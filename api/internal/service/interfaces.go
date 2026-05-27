// Repository interfaces consumed by services. Concrete implementations live
// in internal/repository. Keeping interfaces here (in the service package)
// makes dependency-inversion explicit: service defines what it needs,
// repository fulfills it.
package service

import (
	"context"
	"time"

	"github.com/dplata/mlbsims-api/internal/domain"
)

// LLMRepo handles all Anthropic API interactions.
type LLMRepo interface {
	// GenerateSQL returns the SQL string Claude produced for the question.
	// May return an error if Anthropic is unreachable or rate-limited upstream.
	GenerateSQL(ctx context.Context, question string) (string, error)

	// StreamSummary streams a natural-language explanation of the result set.
	// Caller iterates the channel; channel closes when streaming is done or
	// an error occurs (check Err()).
	StreamSummary(ctx context.Context, question, sql string, rows []domain.Row) (<-chan string, error)
}

// PitchesRepo runs read-only SQL against the pitches table.
type PitchesRepo interface {
	// Execute runs the safe SQL with statement_timeout = timeout.
	// Returns rows or an error (timeout, syntax, missing column, etc).
	Execute(ctx context.Context, sql string, timeout time.Duration) ([]domain.Row, error)
}

// QueriesRepo writes to the queries log table and answers rate-limit lookups.
type QueriesRepo interface {
	CountForIP(ctx context.Context, ipHash string, window time.Duration) (int, error)
	Log(ctx context.Context, log domain.QueryLog) error
}

// CacheRepo is the in-process LRU for recent question→answer pairs.
type CacheRepo interface {
	Get(question string) (domain.Answer, bool)
	Set(question string, answer domain.Answer)
}
