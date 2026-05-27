// Core types shared across layers. Has no external dependencies — neither
// gin, nor pgx, nor anthropic-sdk-go appears here.
package domain

import "time"

// Row is one record returned from the pitches table — column name → value.
// Values come back from pgx as strings/numbers/nil; the controller serializes
// them to JSON without further interpretation.
type Row map[string]any

// Answer is what a successful Ask call returns. The summary is streamed
// separately via SSE; this struct holds the cacheable data part.
type Answer struct {
	Question string `json:"question"`
	SQL      string `json:"sql"`
	Rows     []Row  `json:"rows"`
}

// QueryLog is one row in the queries table.
type QueryLog struct {
	IPHash       string
	Question     string
	GeneratedSQL string
	RowsReturned int
	Status       string // "ok" | "unsafe_sql" | "sql_error" | "timeout" | "llm_error" | "rate_limited" | "cached"
	LatencyMs    int
	Model        string
	Cached       bool
	Timestamp    time.Time
}
