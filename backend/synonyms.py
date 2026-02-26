"""
Skill and keyword synonym expansion for search.

Each group is a set of interchangeable terms. When a user searches for any
member of a group (keyword or skills filter), the search expands to match
any member of that group.

Examples:
  "JS"         → ["JS", "JavaScript"]
  "k8s"        → ["k8s", "Kubernetes"]
  "Postgres"   → ["Postgres", "PostgreSQL"]
"""

# Each inner list is one equivalence group (all spellings / abbreviations).
_GROUPS: list[list[str]] = [
    # JavaScript ecosystem
    ["JavaScript", "JS"],
    ["TypeScript", "TS"],
    ["Node.js", "NodeJS", "Node"],
    ["React", "ReactJS", "React.js"],
    ["Vue.js", "VueJS", "Vue"],
    ["Angular", "AngularJS"],
    ["Next.js", "NextJS", "Next"],
    ["Nuxt.js", "NuxtJS", "Nuxt"],

    # Infrastructure / DevOps
    ["Kubernetes", "k8s"],
    ["CI/CD", "CICD"],
    ["Amazon Web Services", "AWS"],
    ["Google Cloud Platform", "GCP", "Google Cloud"],
    ["Microsoft Azure", "Azure"],

    # Databases
    ["PostgreSQL", "Postgres"],
    ["MongoDB", "Mongo"],
    ["Elasticsearch", "ES"],

    # AI / ML
    ["Machine Learning", "ML"],
    ["Artificial Intelligence", "AI"],
    ["Deep Learning", "DL"],
    ["Natural Language Processing", "NLP"],
    ["Computer Vision", "CV"],
    ["Large Language Model", "LLM"],
    ["Generative AI", "GenAI"],

    # Misc languages / tools
    ["Python", "Py"],
    ["Golang", "Go"],
    ["C++", "CPP"],
]

# Build a lowercase lookup: each term → the full group it belongs to.
# e.g. "js" → ["JavaScript", "JS"], "javascript" → ["JavaScript", "JS"]
_LOOKUP: dict[str, list[str]] = {}
for _group in _GROUPS:
    for _term in _group:
        _LOOKUP[_term.lower()] = _group


def get_skill_synonyms(skill: str) -> list[str]:
    """
    Return all equivalent terms for a skill (original case, including itself).
    If no synonym group exists, returns [skill].
    """
    return _LOOKUP.get(skill.lower(), [skill])


def expand_skills(skills: list[str]) -> list[list[str]]:
    """
    Expand a list of requested skills into synonym groups.

    Returns a list of lists — one inner list per requested skill.
    The SQL layer ORs within each group and ANDs between groups so that
    multi-skill filters narrow results while still matching any spelling.

    Example:
        ["JS", "Python"] → [["JS", "JavaScript"], ["Python", "Py"]]
    """
    return [get_skill_synonyms(s) for s in skills]


def build_fts_conditions(tokens: list[str], mode: str) -> tuple[list[str], list]:
    """
    Build SQL WHERE conditions for FTS with synonym expansion.

    Strategy:
      - mode='or'  → one big websearch_to_tsquery call, all synonym variants ORed.
      - mode='and' → one websearch_to_tsquery condition per token, each ORing its
                     synonyms internally; all conditions ANDed in WHERE.

    Returns (conditions, params).  If no token has a known synonym, returns
    ([], []) so the caller falls back to its default websearch_to_tsquery path.
    """
    if not tokens:
        return [], []

    expanded = [(t, _LOOKUP.get(t.lower(), [t])) for t in tokens]
    has_synonyms = any(len(syns) > 1 for _, syns in expanded)
    if not has_synonyms:
        return [], []   # Nothing to expand — use default path

    _FTS = "to_tsvector('english', COALESCE(raw_text, '')) @@ websearch_to_tsquery('english', %s)"

    if mode == "or":
        # Flatten all synonyms into one OR query
        all_terms: list[str] = []
        for _, syns in expanded:
            all_terms.extend(syns)
        return [_FTS], [" OR ".join(all_terms)]

    else:  # AND — one condition per token, synonyms ORed within
        conditions, params = [], []
        for _, syns in expanded:
            conditions.append(_FTS)
            params.append(" OR ".join(syns))
        return conditions, params
