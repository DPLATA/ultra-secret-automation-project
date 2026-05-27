// AskService orchestrates the full flow of answering a user question.
// It depends only on the interfaces in interfaces.go — no HTTP, no DB driver,
// no Anthropic SDK appear here.
package service

import (
	"context"
	"log/slog"
	"time"

	"github.com/dplata/mlbsims-api/internal/config"
	"github.com/dplata/mlbsims-api/internal/domain"
	"github.com/dplata/mlbsims-api/internal/repository"
)

type AskDeps struct {
	LLM     LLMRepo
	Pitches PitchesRepo
	Queries QueriesRepo
	Cache   CacheRepo
	Config  *config.Config
}

type AskService struct {
	deps AskDeps
}

func NewAskService(deps AskDeps) *AskService {
	return &AskService{deps: deps}
}

// Ask is the main entry point. Returns a populated Answer on success, or
// a domain sentinel error (ErrRateLimitExceeded, ErrUnsafeSQL, etc).
//
// Note: the natural-language summary is NOT in the returned Answer.
// The controller calls StreamSummary separately to emit SSE chunks to the
// client; this method blocks only long enough to produce the data part.
func (s *AskService) Ask(ctx context.Context, ipHash, question string) (*domain.Answer, error) {
	start := time.Now()

	if s.deps.Config.LLMDisabled {
		return nil, domain.ErrFeatureDisabled
	}

	// 1. Rate limit by IP (counts queries in last 24h)
	count, err := s.deps.Queries.CountForIP(ctx, ipHash, 24*time.Hour)
	if err != nil {
		slog.Warn("rate-limit lookup failed; allowing", "err", err)
		// Fail-open: don't block the user on infra issues.
	}
	if count >= s.deps.Config.RateLimitPerDay {
		s.logAsync(ctx, ipHash, question, "", 0, "rate_limited", time.Since(start), false)
		return nil, domain.ErrRateLimitExceeded
	}

	// 2. Cache hit — return immediately, log as cached
	if cached, ok := s.deps.Cache.Get(question); ok {
		s.logAsync(ctx, ipHash, question, cached.SQL, len(cached.Rows), "ok", time.Since(start), true)
		return &cached, nil
	}

	// 3. Ask the LLM to write SQL
	rawSQL, err := s.deps.LLM.GenerateSQL(ctx, question)
	if err != nil {
		s.logAsync(ctx, ipHash, question, "", 0, "llm_error", time.Since(start), false)
		return nil, domain.ErrLLMUnavailable
	}

	// 4. Safety layer — pure function, no I/O
	safeSQL, err := repository.PrepareSafeSQL(rawSQL, s.deps.Config.RowLimit)
	if err != nil {
		s.logAsync(ctx, ipHash, question, rawSQL, 0, "unsafe_sql", time.Since(start), false)
		return nil, domain.ErrUnsafeSQL
	}

	// 5. Execute against Postgres with statement_timeout
	rows, err := s.deps.Pitches.Execute(ctx, safeSQL, s.deps.Config.QueryTimeout)
	if err != nil {
		s.logAsync(ctx, ipHash, question, safeSQL, 0, "sql_error", time.Since(start), false)
		return nil, domain.ErrSQLExecution
	}

	// 6. Build the answer, cache it, log success
	answer := &domain.Answer{
		Question: question,
		SQL:      safeSQL,
		Rows:     rows,
	}
	s.deps.Cache.Set(question, *answer)
	s.logAsync(ctx, ipHash, question, safeSQL, len(rows), "ok", time.Since(start), false)
	return answer, nil
}

// StreamSummary delegates to the LLM repo. Returned channel sends summary
// chunks as Claude generates them; closes when done.
func (s *AskService) StreamSummary(ctx context.Context, answer *domain.Answer) (<-chan string, error) {
	return s.deps.LLM.StreamSummary(ctx, answer.Question, answer.SQL, answer.Rows)
}

// logAsync writes to the queries table in a goroutine so the user response
// is not blocked on the log INSERT. context.Background() is used because
// the request context may be cancelled before the log finishes.
func (s *AskService) logAsync(
	_ context.Context,
	ipHash, question, sql string,
	rowsReturned int,
	status string,
	latency time.Duration,
	cached bool,
) {
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		err := s.deps.Queries.Log(ctx, domain.QueryLog{
			IPHash:       ipHash,
			Question:     question,
			GeneratedSQL: sql,
			RowsReturned: rowsReturned,
			Status:       status,
			LatencyMs:    int(latency.Milliseconds()),
			Model:        s.deps.Config.LLMModel,
			Cached:       cached,
			Timestamp:    time.Now(),
		})
		if err != nil {
			slog.Warn("queries log insert failed", "err", err)
		}
	}()
}
