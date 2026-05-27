// In-process LRU cache for recent question→answer pairs. Cleared on instance
// restart (Cloud Run scales to zero often → cache is mostly cold; that's OK).
//
// For a v1 with 100-1000 questions/day, this is plenty. Move to Memorystore
// (Redis) only if cache hit rate becomes important and traffic warrants it.
package repository

import (
	lru "github.com/hashicorp/golang-lru/v2"

	"github.com/dplata/mlbsims-api/internal/domain"
)

type LRUCache struct {
	c *lru.Cache[string, domain.Answer]
}

func NewLRUCache(size int) *LRUCache {
	c, err := lru.New[string, domain.Answer](size)
	if err != nil {
		// Only errors on size <= 0; safe to panic at startup.
		panic(err)
	}
	return &LRUCache{c: c}
}

func (c *LRUCache) Get(question string) (domain.Answer, bool) {
	return c.c.Get(question)
}

func (c *LRUCache) Set(question string, answer domain.Answer) {
	c.c.Add(question, answer)
}
