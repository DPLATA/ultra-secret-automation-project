package repository

import (
	"strings"
	"testing"
)

func TestPrepareSafeSQL(t *testing.T) {
	tests := []struct {
		name     string
		sql      string
		wantErr  bool
		wantSubs string // substring expected in the returned safe SQL
	}{
		{name: "simple SELECT", sql: "SELECT * FROM pitches WHERE pitcher = 1", wantSubs: "LIMIT 100"},
		{name: "CTE", sql: "WITH x AS (SELECT 1) SELECT * FROM x", wantSubs: "LIMIT 100"},
		{name: "already has LIMIT", sql: "SELECT * FROM pitches LIMIT 5", wantSubs: "LIMIT 5"},
		{name: "trailing semicolon stripped", sql: "SELECT 1;", wantSubs: "LIMIT 100"},

		{name: "INSERT rejected", sql: "INSERT INTO pitches VALUES (1)", wantErr: true},
		{name: "UPDATE rejected", sql: "UPDATE pitches SET batter = 1", wantErr: true},
		{name: "DELETE rejected", sql: "DELETE FROM pitches", wantErr: true},
		{name: "DROP rejected", sql: "DROP TABLE pitches", wantErr: true},
		{name: "multi-statement rejected", sql: "SELECT 1; SELECT 2", wantErr: true},
		{name: "DROP smuggled in CTE", sql: "WITH x AS (SELECT 1) DROP TABLE pitches", wantErr: true},
		{name: "TRUNCATE rejected", sql: "TRUNCATE pitches", wantErr: true},
		{name: "GRANT rejected", sql: "GRANT ALL ON pitches TO public", wantErr: true},
		{name: "COPY rejected", sql: "COPY pitches TO STDOUT", wantErr: true},
		{name: "SET ROLE rejected", sql: "SELECT 1; SET ROLE postgres", wantErr: true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := PrepareSafeSQL(tc.sql, 100)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got safe SQL: %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if tc.wantSubs != "" && !strings.Contains(got, tc.wantSubs) {
				t.Fatalf("expected %q to contain %q", got, tc.wantSubs)
			}
		})
	}
}
