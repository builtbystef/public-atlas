"""The naming rules as logic: the designators, connectors and list forms that decide when two
spellings are one name. `schemas.NamingRules` is the data; this reads it."""

import re

from public_atlas.modules.countries.schemas import NamingRules
from public_atlas.shared.text import name_key, normalize_text

_LIST_PUNCTUATION = dict.fromkeys(map(ord, ',.;:()[]"!?'), " ")


def _plain(text: str) -> str:
    """A name as `forms` compares it: normalized, with list punctuation as spaces."""
    return " ".join(normalize_text(text.translate(_LIST_PUNCTUATION)).split())


class Naming:
    """How a country writes its public bodies' names, in its languages. A government's name is a
    place name with a designator around it ("Township of Elmwood", "Elmwood, Township of");
    knowing the designators lets the checks find the place name and tell a township from the
    city of the same name."""

    def __init__(self, rules: NamingRules) -> None:
        self.rules = rules
        # Each designator with the groups it is in, the longest first, so a two-word designator
        # does not also count as its last word.
        phrases: dict[str, set[int]] = {}
        for group, words in enumerate(rules.designators):
            for word in words:
                phrases.setdefault(name_key(word), set()).add(group)
        self._phrases = sorted(phrases.items(), key=lambda item: -len(item[0]))
        self._connectors = sorted((name_key(c) for c in rules.connectors), key=len, reverse=True)
        self._leading = sorted((name_key(w) for w in rules.leading), key=len, reverse=True)
        self._list_form = self._compile_list_form()
        self._before, self._after = self._compile_kind_patterns()

    def key(self, text: str) -> str:
        """`name_key`, with each of the and-words read as "&"."""
        key = f" {name_key(text)} "
        for word in self.rules.and_words:
            key = key.replace(f" {name_key(word)} ", " & ")
        return key.strip()

    def without_leading(self, key: str) -> str:
        for word in self._leading:
            if key.startswith(f"{word} "):
                return key.removeprefix(f"{word} ").strip()
        return key

    def designators_in(self, text: str) -> set[int]:
        """The designator groups whose words `text` uses as whole words."""
        found: set[int] = set()
        rest = f" {name_key(text)} "
        for phrase, groups in self._phrases:
            if f" {phrase} " in rest:
                found |= groups
                rest = rest.replace(f" {phrase} ", " | ")
        return found

    def core(self, text: str) -> str:
        """The place name inside a government's name: "Township of Elmwood", "Elmwood Township"
        and "Elmwood, Township of" are all "elmwood". A name with no designator is its own
        core."""
        key = self.without_leading(self.key(text))
        for phrase, _ in self._phrases:
            for connector in self._connectors:
                if key.startswith(f"{phrase} {connector} "):
                    return self.without_leading(key.removeprefix(f"{phrase} {connector} "))
                if key.endswith(f", {phrase} {connector}"):
                    return key.removesuffix(f", {phrase} {connector}").strip()
            if key.endswith(f", {phrase}"):
                return key.removesuffix(f", {phrase}").strip()
            if key.endswith(f" {phrase}") and key != phrase:
                return key.removesuffix(f" {phrase}").strip()
        return key

    def designators_differ(self, names: list[str], others: list[str]) -> bool:
        """Whether both sides carry designators and share none: a city and a township with one
        place name."""
        mine = set().union(*(self.designators_in(name) for name in names))
        theirs = set().union(*(self.designators_in(name) for name in others))
        return bool(mine) and bool(theirs) and not mine & theirs

    def written_forms(self, name: str) -> list[str]:
        """The forms a name is written in. A list's "Elmwood, Town of" is "Town of Elmwood" and
        "Elmwood"; any other name is itself."""
        name = " ".join(name.split())
        match = self._list_form.match(name) if self._list_form else None
        if match is None:
            return [name]
        base, kind = match.group("base").strip(), match.group("kind").strip()
        return [f"{kind} {base}", base]

    def plain_forms(self, name: str) -> frozenset[str]:
        """A name as written and without its leading words, uninverted from a list's form, but
        with its designator kept: "Galesburg City" is "galesburg city", never "galesburg". What
        a list's own name of a place is compared in against another place's `forms`."""
        forms: set[str] = set()
        for form in self.written_forms(name):
            plain = _plain(form)
            forms.update((plain, self.without_leading(plain)))
        return frozenset(form for form in forms if form)

    def forms(self, name: str) -> frozenset[str]:
        """The forms a place's name is compared in: as written, uninverted from a list's form,
        and without the leading words and the designator, so "City of Elmwood", "Elmwood, City
        of" and "Elmwood" all meet. Both sides go through this, so what matters is that the same
        name lands on the same forms."""
        forms: set[str] = set()
        for form in self.written_forms(name):
            plain = _plain(form)
            forms.update((plain, self.without_leading(plain)))
            if self._before is not None:
                forms.add(self._before.sub("", plain, count=1))
            if self._after is not None:
                forms.add(self.without_leading(self._after.sub("", plain, count=1)))
        return frozenset(form for form in forms if form)

    def _compile_list_form(self) -> re.Pattern[str] | None:
        """A list's inverted form: the name, a comma, the kind (a few words ending in a
        connector), and sometimes the name again ("Elmwood, Township of Elmwood"). The name may
        hold a comma of its own; the kind has none."""
        if not self.rules.connectors:
            return None
        connectors = "|".join(
            re.escape(c) for c in sorted(self.rules.connectors, key=len, reverse=True)
        )
        return re.compile(
            rf"^(?P<base>.+?),\s+(?P<kind>(?:[^\s,]+\s+){{1,4}}(?:{connectors}))(?:\s+(?P=base))?$",
            re.IGNORECASE,
        )

    def _compile_kind_patterns(self) -> tuple[re.Pattern[str] | None, re.Pattern[str] | None]:
        """The kind of government before a plain name ("corporation of the city of", "ville
        de") and the designator after it ("elmwood county")."""
        before = None
        if self.rules.connectors:
            leading = "".join(f"(?:{re.escape(_plain(w))} )?" for w in self.rules.leading)
            # A connector that ends in an apostrophe ("d'") runs into the name.
            joins = "|".join(
                re.escape(c) if c.endswith("'") else f"{re.escape(c)} "
                for c in sorted((_plain(c) for c in self.rules.connectors), key=len, reverse=True)
            )
            before = re.compile(rf"^{leading}(?:\S+ ){{1,4}}(?:{joins})")
        phrases = "|".join(re.escape(_plain(p)) for p, _ in self._phrases)
        after = re.compile(rf" (?:{phrases})$") if phrases else None
        return before, after
