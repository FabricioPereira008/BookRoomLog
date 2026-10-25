"""Tradução das categorias/assuntos das APIs (em inglês, genéricos e ruidosos) para gêneros em português."""
import re
import unicodedata
from typing import Iterable, List, Optional

MAX_GENRES = 2
GENERIC_FICTION = "Ficção"
# Gênero secundário só entra se for relevante: os assuntos da Open Library trazem muito ruído
SECONDARY_MIN_HITS = 3
SECONDARY_MIN_SHARE = 0.25

# Gênero -> termos que o indicam (comparados sem acentos e em minúsculas, como palavra/expressão inteira).
# A ordem importa no desempate: os mais específicos vêm primeiro.
GENRE_KEYWORDS = {
    "Ficção científica": ["science fiction", "sci-fi", "ficcao cientifica", "dystopia", "dystopian", "space opera",
                          "cyberpunk", "time travel", "robots", "extraterrestrial", "aliens"],
    "Fantasia": ["fantasy", "fantasia", "magic", "magia", "wizards", "magos", "witches", "dragons", "elves",
                 "fairies", "mythical creatures", "sword and sorcery", "epic fantasy"],
    "Terror": ["horror", "terror", "ghosts", "vampires", "zombies", "supernatural", "occult", "haunted houses"],
    "Policial": ["detective", "detectives", "crime", "mystery", "mysteries", "misterio", "policial", "murder",
                 "private investigators", "police"],
    "Suspense": ["thriller", "thrillers", "suspense", "espionage", "spy stories", "psychological fiction"],
    "Romance": ["romance", "love stories", "love story", "romantic", "historias de amor"],
    "Aventura": ["adventure", "adventure stories", "aventura", "action and adventure", "survival"],
    "HQ / Quadrinhos": ["comics", "graphic novels", "comic books", "manga", "quadrinhos", "historias em quadrinhos"],
    "Poesia": ["poetry", "poesia", "poems", "poemas"],
    "Infantojuvenil": ["juvenile fiction", "juvenile literature", "young adult", "children's stories",
                       "children's fiction", "infantojuvenil", "literatura infantil", "literatura juvenil",
                       "school stories"],
    "Clássico": ["classics", "classic literature", "classicos", "literary collections"],
    "Biografia": ["biography", "biography & autobiography", "autobiography", "memoir", "memoirs", "biografia"],
    "História": ["history", "historia", "world war", "historical"],
    "Autoajuda": ["self-help", "self help", "autoajuda", "personal growth", "motivational", "success"],
    "Negócios": ["business", "business & economics", "economics", "management", "finance", "negocios",
                 "entrepreneurship", "investments"],
    "Filosofia": ["philosophy", "filosofia", "ethics", "stoicism"],
    "Religião": ["religion", "religiao", "christianity", "spirituality", "bible", "theology"],
    "Ciência": ["science", "ciencia", "physics", "biology", "mathematics", "astronomy", "psychology",
                "neuroscience", "technology", "computers"],
    "Não ficção": ["nonfiction", "non-fiction", "nao ficcao", "true crime", "essays", "journalism"],
}
# "Fiction" sozinho diz pouco: só vira "Ficção" se nada mais específico aparecer
GENERIC_TERMS = ["fiction", "ficcao", "literary fiction", "fiction in english", "novel", "novels", "romances"]


def fold(text: Optional[str]) -> str:
    """Minúsculas e sem acentos."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _terms(categories: Iterable[str]) -> List[str]:
    """Quebra "Juvenile Fiction / Fantasy / Epic" em partes, sem a tag series: da Open Library."""
    parts = []
    for raw in categories or []:
        if not raw or fold(raw).startswith("series:"):
            continue
        parts.append(fold(raw))
        parts.extend(fold(p).strip() for p in re.split(r"[/,;&]|--", raw) if p.strip())
    return parts


def _pattern(keyword: str) -> "re.Pattern":
    return re.compile(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])")


# Termos mais longos primeiro: "science fiction" consome o trecho antes de "science" (Ciência) ser testado
_KEYWORDS = sorted(((_pattern(k), genre, order) for order, (genre, ks) in enumerate(GENRE_KEYWORDS.items())
                    for k in ks), key=lambda item: -len(item[0].pattern))
_GENERIC = [_pattern(k) for k in GENERIC_TERMS]


def map_genres(categories: Iterable[str], existing_names: Iterable[str] = (), limit: int = MAX_GENRES) -> List[str]:
    """Até `limit` gêneros em português, do que mais casou para o menos. Usa a grafia de `existing_names`
    quando o usuário já tem um gênero com o mesmo nome (sem diferenciar maiúsculas e acentos)."""
    scores = {}
    generic = False
    for term in _terms(categories):
        for pattern, genre, order in _KEYWORDS:
            term, found = pattern.subn(" ", term)
            if found:
                hits, _ = scores.get(genre, (0, 0))
                scores[genre] = (hits + 1, -order)
        generic = generic or any(p.search(term) for p in _GENERIC)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_hits = ordered[0][1][0] if ordered else 0
    ranked = [g for i, (g, (hits, _)) in enumerate(ordered)
              if i == 0 or (hits >= SECONDARY_MIN_HITS and hits >= top_hits * SECONDARY_MIN_SHARE)]
    if not ranked and generic:
        ranked = [GENERIC_FICTION]
    return with_existing_spelling(ranked[:limit], existing_names)


def with_existing_spelling(genres: Iterable[str], existing_names: Iterable[str]) -> List[str]:
    """Troca cada gênero pelo já cadastrado com o mesmo nome (sem diferenciar maiúsculas e acentos)."""
    existing = {fold(name): name for name in existing_names or [] if name}
    return [existing.get(fold(g), g) for g in genres]
