// LLMRepo — talks to OpenRouter (OpenAI-compatible chat completions API).
//
// OpenRouter gives us one endpoint + one API key for many providers. The
// active model is set via LLM_MODEL env var (e.g. "anthropic/claude-haiku-4.5",
// "openai/gpt-4o-mini", "google/gemini-2.5-flash"). Swappable without code change.
//
// Two methods:
//   - GenerateSQL: one-shot completion; returns the SQL string.
//   - StreamSummary: streaming completion; returns a channel of text chunks.
//
// Prompt caching (Anthropic-only feature via OpenRouter) is NOT enabled in v1.
// If costs warrant it later, add `cache_control: ephemeral` on the system
// message — OpenRouter passes that through to Anthropic providers.
package repository

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/dplata/mlbsims-api/internal/config"
	"github.com/dplata/mlbsims-api/internal/domain"
	"github.com/dplata/mlbsims-api/internal/llm_assets"
)

type LLMRepo struct {
	apiKey         string
	baseURL        string
	model          string
	http           *http.Client
	systemPrompt   string // assembled once at startup
	summaryPrompt  string // shorter prompt for the explain-the-results step
}

func NewLLMRepo(cfg *config.Config) *LLMRepo {
	return &LLMRepo{
		apiKey:        cfg.OpenRouterAPIKey,
		baseURL:       cfg.OpenRouterBaseURL,
		model:         cfg.LLMModel,
		http:          &http.Client{},
		systemPrompt:  buildSQLSystemPrompt(llm_assets.SchemaDoc, llm_assets.FewShotJSON),
		summaryPrompt: buildSummarySystemPrompt(),
	}
}

// ----- OpenAI/OpenRouter chat completion request/response types -----

type chatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type chatRequest struct {
	Model       string        `json:"model"`
	Messages    []chatMessage `json:"messages"`
	Stream      bool          `json:"stream,omitempty"`
	MaxTokens   int           `json:"max_tokens,omitempty"`
	Temperature float64       `json:"temperature,omitempty"`
}

type chatResponse struct {
	Choices []struct {
		Message chatMessage `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

// Streaming response chunk (SSE-formatted, but each data: line is JSON)
type chatChunk struct {
	Choices []struct {
		Delta struct {
			Content string `json:"content"`
		} `json:"delta"`
	} `json:"choices"`
}

// ----- GenerateSQL -----

func (r *LLMRepo) GenerateSQL(ctx context.Context, question string) (string, error) {
	reqBody := chatRequest{
		Model: r.model,
		Messages: []chatMessage{
			{Role: "system", Content: r.systemPrompt},
			{Role: "user", Content: question},
		},
		MaxTokens:   800,
		Temperature: 0,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, "POST", r.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+r.apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("HTTP-Referer", "https://mlbsims.com")
	req.Header.Set("X-Title", "MLB Sims Ask")

	resp, err := r.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("openrouter request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		raw, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("openrouter status %d: %s", resp.StatusCode, string(raw))
	}

	var cr chatResponse
	if err := json.NewDecoder(resp.Body).Decode(&cr); err != nil {
		return "", err
	}
	if cr.Error != nil {
		return "", errors.New(cr.Error.Message)
	}
	if len(cr.Choices) == 0 {
		return "", errors.New("empty response from LLM")
	}
	return cleanSQL(cr.Choices[0].Message.Content), nil
}

// ----- StreamSummary -----

func (r *LLMRepo) StreamSummary(ctx context.Context, question, sql string, rows []domain.Row) (<-chan string, error) {
	userMsg := fmt.Sprintf(
		"Question: %s\n\nSQL run:\n%s\n\nResults (JSON):\n%s\n\nExplain these results in 2-4 plain English sentences.",
		question, sql, jsonRowsTruncated(rows, 20),
	)
	reqBody := chatRequest{
		Model: r.model,
		Messages: []chatMessage{
			{Role: "system", Content: r.summaryPrompt},
			{Role: "user", Content: userMsg},
		},
		Stream:      true,
		MaxTokens:   400,
		Temperature: 0.4,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, "POST", r.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+r.apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("HTTP-Referer", "https://mlbsims.com")
	req.Header.Set("X-Title", "MLB Sims Ask")

	resp, err := r.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("openrouter stream request: %w", err)
	}
	if resp.StatusCode != 200 {
		raw, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		return nil, fmt.Errorf("openrouter stream status %d: %s", resp.StatusCode, string(raw))
	}

	out := make(chan string, 32)
	go func() {
		defer resp.Body.Close()
		defer close(out)
		scanner := bufio.NewScanner(resp.Body)
		scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
		for scanner.Scan() {
			line := scanner.Text()
			if !strings.HasPrefix(line, "data: ") {
				continue
			}
			payload := strings.TrimPrefix(line, "data: ")
			if payload == "[DONE]" {
				return
			}
			var chunk chatChunk
			if err := json.Unmarshal([]byte(payload), &chunk); err != nil {
				continue
			}
			if len(chunk.Choices) > 0 {
				if delta := chunk.Choices[0].Delta.Content; delta != "" {
					select {
					case out <- delta:
					case <-ctx.Done():
						return
					}
				}
			}
		}
	}()
	return out, nil
}

// ----- Prompt builders -----

func buildSQLSystemPrompt(schema, fewShot string) string {
	var sb strings.Builder
	sb.WriteString("You are an MLB Statcast SQL writer.\n")
	sb.WriteString("Given a natural-language question, return ONE Postgres SELECT query that answers it.\n\n")
	sb.WriteString("Output contract:\n")
	sb.WriteString("- Return ONLY the SQL — no markdown fences, no explanation, no leading text.\n")
	sb.WriteString("- Must start with SELECT or WITH.\n")
	sb.WriteString("- Must be a single statement.\n")
	sb.WriteString("- Never use INSERT/UPDATE/DELETE/DROP/etc.\n")
	sb.WriteString("- Include a reasonable LIMIT (10-25) unless the question requires more.\n\n")
	sb.WriteString("=== SCHEMA ===\n")
	sb.WriteString(schema)
	sb.WriteString("\n\n=== EXAMPLES ===\n")
	sb.WriteString(fewShot)
	return sb.String()
}

func buildSummarySystemPrompt() string {
	return strings.TrimSpace(`
You are explaining MLB Statcast query results to a baseball fan.
Read the question, the SQL that was run, and the rows it returned.
Write a tight 2-4 sentence summary in plain English. Highlight the
single most interesting number or pattern. Don't restate the SQL.
Don't apologize for limitations of the data. Be direct.`)
}

// ----- helpers -----

// cleanSQL strips markdown fences / leading "sql:" labels the LLM sometimes adds.
func cleanSQL(s string) string {
	s = strings.TrimSpace(s)
	s = strings.TrimPrefix(s, "```sql")
	s = strings.TrimPrefix(s, "```")
	s = strings.TrimSuffix(s, "```")
	s = strings.TrimSpace(s)
	return s
}

// jsonRowsTruncated serializes up to maxRows for the explain step. We don't
// want to flood the model with 100 rows of data; the top N tell the story.
func jsonRowsTruncated(rows []domain.Row, maxRows int) string {
	if len(rows) > maxRows {
		rows = rows[:maxRows]
	}
	b, err := json.Marshal(rows)
	if err != nil {
		return "[]"
	}
	return string(b)
}
