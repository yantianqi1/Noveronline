package assets

import (
	"strings"
	"unicode"
)

// Application-layer tokenization for keyword matching. to_tsvector('simple')
// cannot segment CJK text, and a single whole-query ILIKE fails as soon as the
// query has more than one term ("许七安 的 师门" → zero hits even though 许七安
// matches hundreds of rows). The query is split into terms here and matched
// term-by-term in SQL, scored by the fraction of terms hit. Mirrors the Pi
// runtime tokenizer (apps/pi-agent-runtime postgres-pi-writer-deps.ts) so the
// asset library search and Agent recall rank the same way.
const (
	searchTermMax    = 8
	searchTermMinLen = 2 // runes
)

// Single-character CJK function words that safely delimit unsegmented runs
// ("许七安的师门" → 许七安 / 师门). Fragments still substring-match full names
// in ILIKE, so over-splitting only costs precision, never recall.
const cjkSplitChars = "的了和与或在是就都而被把向从对于以并也又还让"

var searchStopwords = buildSearchStopwords()

func buildSearchStopwords() map[string]bool {
	stopwords := map[string]bool{
		"这": true, "那": true, "一个": true, "什么": true, "怎么": true,
		"the": true, "a": true, "an": true, "of": true, "to": true, "and": true,
		"or": true, "in": true, "on": true, "for": true, "with": true, "at": true,
		"by": true, "is": true, "are": true,
	}
	for _, r := range cjkSplitChars {
		stopwords[string(r)] = true
	}
	return stopwords
}

func isCJKSplitRune(r rune) bool {
	return strings.ContainsRune(cjkSplitChars, r)
}

func containsCJK(token string) bool {
	for _, r := range token {
		if r >= 0x3400 && r <= 0x9FFF {
			return true
		}
	}
	return false
}

// TokenizeSearchQuery splits a free-form query into match terms: whitespace and
// punctuation first, then unsegmented CJK runs on single-character function
// words. Falls back to the whole trimmed query when nothing survives.
func TokenizeSearchQuery(query string) []string {
	trimmed := strings.TrimSpace(query)
	if trimmed == "" {
		return nil
	}
	terms := make([]string, 0, searchTermMax)
	seen := map[string]bool{}
	push := func(raw string) {
		token := strings.TrimSpace(raw)
		if len([]rune(token)) < searchTermMinLen {
			return
		}
		lower := strings.ToLower(token)
		if searchStopwords[lower] || seen[lower] {
			return
		}
		seen[lower] = true
		if len(terms) < searchTermMax {
			terms = append(terms, token)
		}
	}
	tokens := strings.FieldsFunc(trimmed, func(r rune) bool {
		return unicode.IsSpace(r) || unicode.IsPunct(r) || unicode.IsSymbol(r)
	})
	for _, token := range tokens {
		if containsCJK(token) && strings.ContainsFunc(token, isCJKSplitRune) {
			for _, fragment := range strings.FieldsFunc(token, isCJKSplitRune) {
				push(fragment)
			}
			continue
		}
		push(token)
	}
	if len(terms) == 0 {
		return []string{trimmed}
	}
	return terms
}

var searchLikeEscaper = strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)

// searchLikePatterns wraps each term in ILIKE wildcards with LIKE metacharacters
// escaped, ready to bind as a text[] parameter.
func searchLikePatterns(terms []string) []string {
	patterns := make([]string, 0, len(terms))
	for _, term := range terms {
		patterns = append(patterns, "%"+searchLikeEscaper.Replace(term)+"%")
	}
	return patterns
}
