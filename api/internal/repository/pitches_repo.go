// PitchesRepo executes LLM-generated SQL against the pitches table.
// Always read-only (DB role is mlbsims_llm with SELECT-only grants);
// statement_timeout enforced per-query.
package repository

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/dplata/mlbsims-api/internal/domain"
)

type PitchesRepo struct {
	pool *pgxpool.Pool
}

func NewPitchesRepo(pool *pgxpool.Pool) *PitchesRepo {
	return &PitchesRepo{pool: pool}
}

// Execute runs the safe SQL with statement_timeout = timeout.
// Returns rows as a slice of column→value maps, ready to serialize.
func (r *PitchesRepo) Execute(ctx context.Context, sql string, timeout time.Duration) ([]domain.Row, error) {
	conn, err := r.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("acquire conn: %w", err)
	}
	defer conn.Release()

	// Bound the query duration server-side. SET LOCAL only affects this txn.
	tx, err := conn.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	_, err = tx.Exec(ctx, fmt.Sprintf("SET LOCAL statement_timeout = '%dms'", timeout.Milliseconds()))
	if err != nil {
		return nil, fmt.Errorf("set timeout: %w", err)
	}

	rows, err := tx.Query(ctx, sql)
	if err != nil {
		return nil, fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	cols := rows.FieldDescriptions()
	out := make([]domain.Row, 0, 16)
	for rows.Next() {
		vals, err := rows.Values()
		if err != nil {
			return nil, fmt.Errorf("scan: %w", err)
		}
		row := make(domain.Row, len(cols))
		for i, c := range cols {
			row[string(c.Name)] = vals[i]
		}
		out = append(out, row)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows iteration: %w", err)
	}
	return out, nil
}
