// Postgres connection setup. Production uses Cloud SQL Go Connector (no
// proxy sidecar). Local dev points DB_HOST at a local cloud-sql-proxy.
package repository

import (
	"context"
	"fmt"
	"log/slog"
	"net"

	"cloud.google.com/go/cloudsqlconn"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/dplata/mlbsims-api/internal/config"
)

// MustNewPgxPool returns a connection pool ready for use.
// When cfg.DBInstance is set (e.g. "project:us-east1:mlbsims-statcast"),
// the Cloud SQL Go Connector handles auth + TLS in-process — no proxy needed.
// When DBInstance is empty, falls back to a regular TCP connection to
// cfg.DBHost:cfg.DBPort (for local dev via cloud-sql-proxy).
func MustNewPgxPool(cfg *config.Config) *pgxpool.Pool {
	dsn := fmt.Sprintf(
		"user=%s password=%s dbname=%s sslmode=disable",
		cfg.DBUser, cfg.DBPassword, cfg.DBName,
	)
	poolCfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		panic(fmt.Sprintf("pgxpool ParseConfig: %v", err))
	}

	if cfg.DBInstance != "" {
		// Production path — Cloud SQL Go Connector
		d, err := cloudsqlconn.NewDialer(context.Background())
		if err != nil {
			panic(fmt.Sprintf("cloudsqlconn.NewDialer: %v", err))
		}
		poolCfg.ConnConfig.DialFunc = func(ctx context.Context, _, _ string) (net.Conn, error) {
			return d.Dial(ctx, cfg.DBInstance)
		}
		// Strip host/port from DSN — Dialer routes via instance name
		poolCfg.ConnConfig.Host = ""
		poolCfg.ConnConfig.Port = 0
		slog.Info("db: using Cloud SQL Go Connector", "instance", cfg.DBInstance)
	} else {
		poolCfg.ConnConfig.Host = cfg.DBHost
		poolCfg.ConnConfig.Port = uint16(parsePort(cfg.DBPort))
		slog.Info("db: using local TCP", "host", cfg.DBHost, "port", cfg.DBPort)
	}

	pool, err := pgxpool.NewWithConfig(context.Background(), poolCfg)
	if err != nil {
		panic(fmt.Sprintf("pgxpool.NewWithConfig: %v", err))
	}

	// Sanity ping
	if err := pool.Ping(context.Background()); err != nil {
		panic(fmt.Sprintf("db ping failed: %v", err))
	}
	return pool
}

func parsePort(s string) int {
	var n int
	fmt.Sscanf(s, "%d", &n)
	if n == 0 {
		n = 5432
	}
	return n
}

// (unused but imported for future SET ROLE / SET statement_timeout hooks)
var _ = pgx.ErrNoRows
