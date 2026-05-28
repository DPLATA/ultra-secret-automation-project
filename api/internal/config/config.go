// Loads + validates environment variables. Single source of truth for runtime config.
package config

import (
	"fmt"
	"log/slog"
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port string

	// OpenRouter — single gateway to many providers (Anthropic, OpenAI, Google, etc).
	// Default model is anthropic/claude-haiku-4.5 but switchable via env var.
	OpenRouterAPIKey  string
	OpenRouterBaseURL string
	LLMModel          string

	// Cloud SQL — when DBInstance is set, use Cloud SQL Connector; otherwise fall back
	// to DBHost/DBPort for local dev via cloud-sql-proxy.
	DBInstance string
	DBHost     string
	DBPort     string
	DBName     string
	DBUser     string
	DBPassword string

	// Security / limits
	IPHashSecret    string
	RateLimitPerDay int
	RowLimit        int
	QueryTimeout    time.Duration

	// Kill switch
	LLMDisabled bool
}

func MustLoad() *Config {
	cfg := &Config{
		Port:              getEnv("PORT", "8080"),
		OpenRouterAPIKey:  mustEnv("OPENROUTER_API_KEY"),
		OpenRouterBaseURL: getEnv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
		// Trial default — switch to "anthropic/claude-haiku-4.5" once we want to pay
		// for higher quality + caching. Override at runtime via LLM_MODEL env var.
		LLMModel:          getEnv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
		DBInstance:        os.Getenv("DB_INSTANCE"),
		DBHost:            getEnv("DB_HOST", "127.0.0.1"),
		DBPort:            getEnv("DB_PORT", "5432"),
		DBName:            getEnv("DB_NAME", "statcast"),
		DBUser:            mustEnv("DB_USER"),
		DBPassword:        mustEnv("DB_PASSWORD"),
		IPHashSecret:      mustEnv("IP_HASH_SECRET"),
		RateLimitPerDay:   getEnvInt("RATE_LIMIT_PER_DAY", 10),
		RowLimit:          getEnvInt("ROW_LIMIT", 100),
		QueryTimeout:      getEnvDuration("QUERY_TIMEOUT", 5*time.Second),
		LLMDisabled:       getEnv("LLM_DISABLED", "") == "1",
	}
	slog.Info("config loaded", "model", cfg.LLMModel, "db_instance", cfg.DBInstance, "rate_limit", cfg.RateLimitPerDay)
	return cfg
}

func mustEnv(k string) string {
	v := os.Getenv(k)
	if v == "" {
		panic(fmt.Sprintf("required env var %s is not set", k))
	}
	return v
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func getEnvInt(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func getEnvDuration(k string, def time.Duration) time.Duration {
	if v := os.Getenv(k); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return def
}
