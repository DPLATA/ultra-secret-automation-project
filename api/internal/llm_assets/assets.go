// Package llm_assets owns the embedded static content the LLM repo loads at
// startup. Lives in its own package because //go:embed cannot use parent-dir
// (../) paths — the embed directive must reference files in the same directory.
package llm_assets

import _ "embed"

//go:embed schema_doc.md
var SchemaDoc string

//go:embed few_shot.json
var FewShotJSON string
