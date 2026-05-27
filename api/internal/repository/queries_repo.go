// QueriesRepo handles the queries log table — both writing logs and
// answering rate-limit lookups (count for IP in last N hours).
//
// The queries table schema lives in db/alembic/versions/0002_queries_table.py
// (to be created).
package repository

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/dplata/mlbsims-api/internal/domain"
)

type QueriesRepo struct {
	pool *pgxpool.Pool
}

func NewQueriesRepo(pool *pgxpool.Pool) *QueriesRepo {
	return &QueriesRepo{pool: pool}
}

// CountForIP returns how many queries this IP hash has made in the given window.
// Used for rate limiting.
func (r *QueriesRepo) CountForIP(ctx context.Context, ipHash string, window time.Duration) (int, error) {
	const q = `
		SELECT count(*)
		FROM queries
		WHERE ip_hash = $1
		  AND ts > now() - $2::interval
	`
	var n int
	intervalStr := fmt.Sprintf("%d seconds", int(window.Seconds()))
	err := r.pool.QueryRow(ctx, q, ipHash, intervalStr).Scan(&n)
	if err != nil {
		return 0, fmt.Errorf("count for ip: %w", err)
	}
	return n, nil
}

// Log inserts one row into the queries table. Called from a goroutine after
// the response is sent so it never blocks the user.
func (r *QueriesRepo) Log(ctx context.Context, l domain.QueryLog) error {
	const q = `
		INSERT INTO queries (
			ts, ip_hash, question, generated_sql,
			rows_returned, status, latency_ms, model, cached
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
	`
	_, err := r.pool.Exec(ctx, q,
		l.Timestamp, l.IPHash, l.Question, l.GeneratedSQL,
		l.RowsReturned, l.Status, l.LatencyMs, l.Model, l.Cached,
	)
	if err != nil {
		return fmt.Errorf("insert query log: %w", err)
	}
	return nil
}
