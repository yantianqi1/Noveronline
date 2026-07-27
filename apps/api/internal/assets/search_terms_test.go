package assets

import (
	"reflect"
	"testing"
)

func TestTokenizeSearchQuerySplitsWhitespaceAndCJKFunctionWords(t *testing.T) {
	tests := []struct {
		name  string
		query string
		want  []string
	}{
		{name: "spaced multi-term", query: "许七安 的 师门", want: []string{"许七安", "师门"}},
		{name: "unsegmented CJK run", query: "许七安的师门", want: []string{"许七安", "师门"}},
		{name: "planner style query", query: "许七安 打更人 司天监 炼金 税银案", want: []string{"许七安", "打更人", "司天监", "炼金", "税银案"}},
		{name: "single term passthrough", query: "青玄剑宗", want: []string{"青玄剑宗"}},
		{name: "latin stopwords dropped", query: "the sect of Xu", want: []string{"sect", "Xu"}},
		{name: "dedupes repeated terms", query: "师门 师门 复命", want: []string{"师门", "复命"}},
		{name: "empty", query: "   ", want: nil},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got := TokenizeSearchQuery(test.query)
			if !reflect.DeepEqual(got, test.want) {
				t.Fatalf("TokenizeSearchQuery(%q) = %#v, want %#v", test.query, got, test.want)
			}
		})
	}
}

func TestTokenizeSearchQueryFallsBackToWholeQuery(t *testing.T) {
	// Nothing survives the min-length filter -> whole trimmed query, so the SQL
	// keeps the old single-pattern behavior instead of matching nothing.
	got := TokenizeSearchQuery("了 的")
	if !reflect.DeepEqual(got, []string{"了 的"}) {
		t.Fatalf("expected whole-query fallback, got %#v", got)
	}
}

func TestSearchLikePatternsEscapesMetacharacters(t *testing.T) {
	got := searchLikePatterns([]string{"50%", "a_b", `c\d`})
	want := []string{`%50\%%`, `%a\_b%`, `%c\\d%`}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("searchLikePatterns = %#v, want %#v", got, want)
	}
}
