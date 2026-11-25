"""Indbygget opskriftsbibliotek og import af opskrifter fra URL.

Alle indbyggede opskrifter er til 4 personer. Hver ingrediens har et
søgeord, som virker godt på nemlig.com.

Ingrediens-format: (søgeord, mængde, enhed, "pantry")
"pantry" betyder, at de fleste har varen i skabet (salt, olie, krydderier).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

P = "pantry"


@dataclass
class Ingredient:
    name: str
    amount: float | None = None
    unit: str = ""
    pantry: bool = False


@dataclass
class Recipe:
    id: str
    title: str
    description: str
    minutes: int
    main: str  # kylling, okse, svin, fisk, vegetar
    tags: list[str] = field(default_factory=list)
    servings: int = 4
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    source_url: str | None = None
    emoji: str = "🍽️"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        d = dict(d)
        d["ingredients"] = [Ingredient(**i) for i in d.get("ingredients", [])]
        return cls(**d)


def _r(id, title, description, minutes, main, emoji, ingredients, steps, tags=()):
    ings = [
        Ingredient(name=i[0], amount=i[1], unit=i[2], pantry=(len(i) > 3 and i[3] == P))
        for i in ingredients
    ]
    return Recipe(
        id=id, title=title, description=description, minutes=minutes, main=main,
        emoji=emoji, ingredients=ings, steps=list(steps), tags=list(tags),
    )


RECIPES: list[Recipe] = [
    _r("kylling-karry", "Cremet kylling i karry", "Mild karry med æble, porre og ris.",
       35, "kylling", "🍛",
       [("kyllingebryst", 600, "g"), ("porre", 1, "stk"), ("æble", 1, "stk"), ("madlavningsfløde", 2.5, "dl"),
        ("ris", 300, "g"), ("karry", 2, "spsk", P), ("hønsebouillon", 1, "stk", P), ("smør", 25, "g")],
       ["Skær kylling, porre og æble i tern.", "Brun kyllingen i smør. Tilsæt karry og porre.",
        "Tilsæt fløde, bouillon og æble. Lad det simre i 15 min.", "Kog risene og server."],
       ["hurtig", "børnevenlig"]),
    _r("bolognese", "Spaghetti bolognese", "Klassisk kødsovs med gulerod og masser af tomat.",
       45, "okse", "🍝",
       [("hakket oksekød", 500, "g"), ("spaghetti", 500, "g"), ("hakkede tomater", 2, "dåse"), ("løg", 1, "stk"),
        ("gulerødder", 2, "stk"), ("hvidløg", 2, "fed"), ("tomatpuré", 1, "stk"), ("parmesan", 100, "g"),
        ("oregano", 1, "tsk", P), ("olivenolie", 2, "spsk", P)],
       ["Hak løg, hvidløg og gulerødder.", "Brun kødet med grøntsagerne i olie.",
        "Tilsæt tomater, puré og oregano. Simr i 25 min.", "Kog spaghetti. Server med revet parmesan."],
       ["børnevenlig"]),
    _r("laks-ovn", "Ovnbagt laks med citron", "Laks, kartofler og broccoli på én bradepande.",
       35, "fisk", "🐟",
       [("laksefilet", 600, "g"), ("kartofler", 1000, "g"), ("broccoli", 1, "stk"), ("citron", 1, "stk"),
        ("creme fraiche", 2, "dl"), ("dild", 1, "stk"), ("olivenolie", 2, "spsk", P)],
       ["Skær kartofler i både. Bag dem i 15 min ved 200 °C.", "Læg laks og broccoli på pladen. Bag 15 min mere.",
        "Rør creme fraiche med dild og citron.", "Server med citronbåde."],
       ["sund"]),
    _r("tacos", "Tacos med oksekød", "Fredagshygge med sprøde skaller og friske grøntsager.",
       25, "okse", "🌮",
       [("hakket oksekød", 500, "g"), ("tacoskaller", 1, "pk"), ("tacokrydderi", 1, "pk"), ("iceberg", 1, "stk"),
        ("tomater", 4, "stk"), ("agurk", 1, "stk"), ("revet ost", 200, "g"), ("creme fraiche", 2, "dl"),
        ("majs", 1, "dåse"), ("salsa", 1, "stk")],
       ["Brun kødet. Tilsæt krydderi og lidt vand.", "Skær grøntsagerne i små stykker.",
        "Varm skallerne i ovnen.", "Sæt det hele på bordet."],
       ["hurtig", "børnevenlig"]),
    _r("frikadeller", "Frikadeller med kartofler", "Hjemmelavede frikadeller med agurkesalat.",
       50, "svin", "🥔",
       [("hakket svinekød", 500, "g"), ("æg", 1, "stk"), ("løg", 1, "stk"), ("mælk", 1, "dl"),
        ("kartofler", 1000, "g"), ("agurk", 1, "stk"), ("smør", 50, "g"), ("hvedemel", 3, "spsk", P),
        ("eddike", 1, "dl", P), ("sukker", 2, "spsk", P)],
       ["Rør farsen med æg, revet løg, mel og mælk.", "Steg frikadellerne i smør i ca. 15 min.",
        "Kog kartoflerne.", "Snit agurken. Vend den med eddike og sukker."],
       ["børnevenlig", "klassiker"]),
    _r("carbonara", "Pasta carbonara", "Cremet uden fløde – kun æg, ost og bacon.",
       20, "svin", "🍝",
       [("spaghetti", 400, "g"), ("bacon", 200, "g"), ("æg", 4, "stk"), ("parmesan", 100, "g"),
        ("peber", 1, "tsk", P)],
       ["Kog pastaen.", "Steg bacon sprødt.", "Pisk æg og revet parmesan.",
        "Vend pasta, bacon og æg sammen af varmen. Krydr med peber."],
       ["hurtig"]),
    _r("vegetarlasagne", "Lasagne med spinat og ricotta", "Grøn lasagne med tomatsovs og mozzarella.",
       60, "vegetar", "🥬",
       [("lasagneplader", 1, "pk"), ("spinat", 450, "g"), ("ricotta", 250, "g"), ("mozzarella", 2, "stk"),
        ("hakkede tomater", 2, "dåse"), ("løg", 1, "stk"), ("hvidløg", 2, "fed"), ("parmesan", 50, "g")],
       ["Lav tomatsovs af løg, hvidløg og tomater.", "Rør spinat og ricotta sammen.",
        "Læg lag af plader, sovs og spinat i et fad.", "Top med mozzarella. Bag 35 min ved 200 °C."],
       ["vegetar"]),
    _r("thai-karry", "Rød thaikarry med kylling", "Kokosmælk, rød karry og sprøde grøntsager.",
       30, "kylling", "🌶️",
       [("kyllingelår", 600, "g"), ("kokosmælk", 2, "dåse"), ("rød karrypasta", 1, "stk"), ("peberfrugt", 2, "stk"),
        ("sukkerærter", 200, "g"), ("jasminris", 300, "g"), ("lime", 1, "stk"), ("koriander", 1, "stk"),
        ("fiskesauce", 2, "spsk", P)],
       ["Steg karrypasta i lidt kokosmælk.", "Tilsæt kylling i strimler. Steg den.",
        "Tilsæt resten af kokosmælken og grøntsagerne. Simr i 10 min.", "Smag til med lime og fiskesauce. Server med ris."],
       ["hurtig", "stærk"]),
    _r("chili-sin-carne", "Chili sin carne", "Mættende bønnechili med ris og creme fraiche.",
       40, "vegetar", "🫘",
       [("kidneybønner", 2, "dåse"), ("sorte bønner", 1, "dåse"), ("hakkede tomater", 2, "dåse"), ("løg", 2, "stk"),
        ("peberfrugt", 2, "stk"), ("hvidløg", 3, "fed"), ("ris", 300, "g"), ("creme fraiche", 2, "dl"),
        ("spidskommen", 1, "tsk", P), ("chili", 1, "tsk", P)],
       ["Steg løg, hvidløg og peberfrugt.", "Tilsæt krydderier, tomater og bønner.",
        "Simr i 25 min.", "Server med ris og creme fraiche."],
       ["vegetar", "billig"]),
    _r("kyllingewraps", "Kyllingewraps", "Hurtige wraps med kylling, salat og dressing.",
       20, "kylling", "🌯",
       [("kyllingebryst", 500, "g"), ("tortilla", 1, "pk"), ("salat", 1, "stk"), ("tomater", 3, "stk"),
        ("rødløg", 1, "stk"), ("avocado", 2, "stk"), ("græsk yoghurt", 2, "dl"), ("paprika", 1, "tsk", P)],
       ["Skær kyllingen i strimler. Steg den med paprika.", "Snit grøntsagerne.",
        "Varm tortillas.", "Fyld dem med kylling, grønt og yoghurt."],
       ["hurtig", "børnevenlig"]),
    _r("torsk-persillesovs", "Torsk med persillesovs", "Mild hvid fisk med kartofler og grøn sovs.",
       35, "fisk", "🐠",
       [("torskefilet", 600, "g"), ("kartofler", 1000, "g"), ("persille", 1, "stk"), ("mælk", 5, "dl"),
        ("smør", 40, "g"), ("gulerødder", 4, "stk"), ("hvedemel", 3, "spsk", P)],
       ["Kog kartofler og gulerødder.", "Damp torsken i 8–10 min.",
        "Lav opbagt sovs af smør, mel og mælk. Tilsæt hakket persille.", "Server det hele sammen."],
       ["klassiker", "sund"]),
    _r("svamperisotto", "Risotto med svampe", "Cremet risotto med champignon og parmesan.",
       40, "vegetar", "🍄",
       [("risottoris", 300, "g"), ("champignon", 400, "g"), ("løg", 1, "stk"), ("hvidvin", 1, "dl"),
        ("grøntsagsbouillon", 2, "stk", P), ("parmesan", 100, "g"), ("smør", 50, "g"), ("timian", 1, "stk")],
       ["Steg svampene. Tag dem af panden.", "Steg løg og ris i smør. Tilsæt vin.",
        "Tilsæt bouillon lidt ad gangen i 20 min.", "Vend svampe, parmesan og smør i."],
       ["vegetar"]),
    _r("burger", "Hjemmelavede burgere", "Saftige bøffer med cheddar og bagte kartofler.",
       40, "okse", "🍔",
       [("hakket oksekød", 600, "g"), ("burgerboller", 1, "pk"), ("cheddar", 150, "g"), ("tomater", 2, "stk"),
        ("salat", 1, "stk"), ("rødløg", 1, "stk"), ("bagekartofler", 1000, "g"), ("dressing", 1, "stk")],
       ["Bag kartoffelbåde i ovnen i 30 min.", "Form 4 bøffer. Steg dem 3–4 min på hver side.",
        "Læg ost på til sidst.", "Byg burgerne med grønt og dressing."],
       ["børnevenlig"]),
    _r("pizza", "Pizza med skinke og champignon", "Hjemmelavet pizza på færdig dej.",
       30, "svin", "🍕",
       [("pizzadej", 2, "stk"), ("tomatsauce", 1, "stk"), ("skinke", 150, "g"), ("champignon", 250, "g"),
        ("mozzarella", 2, "stk"), ("oregano", 1, "tsk", P)],
       ["Rul dejen ud.", "Smør tomatsauce på.", "Fordel skinke, svampe og ost.",
        "Bag 12–15 min ved 250 °C."],
       ["børnevenlig", "hurtig"]),
    _r("shakshuka", "Shakshuka", "Æg bagt i krydret tomatsovs. Server med godt brød.",
       25, "vegetar", "🍳",
       [("æg", 8, "stk"), ("hakkede tomater", 2, "dåse"), ("peberfrugt", 2, "stk"), ("løg", 1, "stk"),
        ("hvidløg", 2, "fed"), ("feta", 150, "g"), ("surdejsbrød", 1, "stk"), ("spidskommen", 1, "tsk", P)],
       ["Steg løg, hvidløg og peberfrugt.", "Tilsæt tomater og krydderi. Simr i 10 min.",
        "Lav huller. Slå æggene i. Læg låg på i 6–8 min.", "Drys med feta. Server med brød."],
       ["vegetar", "hurtig"]),
    _r("morbradgryde", "Mørbradgryde", "Svinemørbrad i flødesovs med champignon og ris.",
       35, "svin", "🥘",
       [("svinemørbrad", 600, "g"), ("champignon", 250, "g"), ("løg", 1, "stk"), ("madlavningsfløde", 2.5, "dl"),
        ("ris", 300, "g"), ("paprika", 1, "tsk", P), ("tomatpuré", 1, "stk"), ("smør", 25, "g")],
       ["Skær mørbraden i skiver. Brun dem i smør.", "Steg løg og svampe.",
        "Tilsæt fløde, puré og paprika. Simr i 15 min.", "Server med ris."],
       ["klassiker"]),
    _r("kylling-rodfrugter", "Ovnstegt kylling med rodfrugter", "Sprøde kyllingelår og bagte rodfrugter.",
       55, "kylling", "🍗",
       [("kyllingelår", 1000, "g"), ("kartofler", 750, "g"), ("gulerødder", 4, "stk"), ("pastinak", 2, "stk"),
        ("rødløg", 2, "stk"), ("rosmarin", 1, "stk"), ("olivenolie", 3, "spsk", P)],
       ["Skær rodfrugter i stykker.", "Læg kylling og grønt på en bradepande med olie og rosmarin.",
        "Bag 45 min ved 200 °C."],
       ["sund"]),
    _r("rejepasta", "Pasta med rejer og chili", "Hvidløg, chili, citron og persille.",
       20, "fisk", "🦐",
       [("tagliatelle", 400, "g"), ("rejer", 400, "g"), ("hvidløg", 3, "fed"), ("chili", 1, "stk"),
        ("citron", 1, "stk"), ("persille", 1, "stk"), ("cherrytomater", 250, "g"), ("olivenolie", 4, "spsk", P)],
       ["Kog pastaen.", "Steg hvidløg og chili i olie.", "Tilsæt tomater og rejer i 2 min.",
        "Vend med pasta, citron og persille."],
       ["hurtig"]),
    _r("linsesuppe", "Rød linsesuppe med kokos", "Varm og billig suppe med naanbrød.",
       30, "vegetar", "🥣",
       [("røde linser", 300, "g"), ("kokosmælk", 1, "dåse"), ("hakkede tomater", 1, "dåse"), ("løg", 1, "stk"),
        ("gulerødder", 2, "stk"), ("ingefær", 1, "stk"), ("naanbrød", 1, "pk"), ("karry", 1, "spsk", P),
        ("grøntsagsbouillon", 1, "stk", P)],
       ["Steg løg, gulerod og ingefær med karry.", "Tilsæt linser, tomater, kokosmælk og 7 dl vand.",
        "Kog i 20 min. Blend let.", "Server med naanbrød."],
       ["vegetar", "billig"]),
    _r("wok-okse", "Wok med oksekød og nudler", "Hurtig wok med strimler af oksekød.",
       25, "okse", "🥢",
       [("oksestrimler", 400, "g"), ("ægnudler", 250, "g"), ("wokgrøntsager", 600, "g"), ("soja", 1, "stk"),
        ("ingefær", 1, "stk"), ("hvidløg", 2, "fed"), ("forårsløg", 1, "stk"), ("sesamolie", 1, "spsk", P)],
       ["Kog nudlerne.", "Steg kødet hurtigt ved høj varme.", "Tilsæt grøntsager, hvidløg og ingefær.",
        "Vend nudler og soja i. Drys med forårsløg."],
       ["hurtig"]),
    _r("fiskefrikadeller", "Fiskefrikadeller med rugbrød", "Hjemmelavede fiskefrikadeller og remoulade.",
       40, "fisk", "🐡",
       [("fiskefars", 500, "g"), ("rugbrød", 1, "stk"), ("remoulade", 1, "stk"), ("citron", 1, "stk"),
        ("salat", 1, "stk"), ("smør", 40, "g"), ("dild", 1, "stk")],
       ["Rør dild i farsen.", "Form frikadeller med en ske.", "Steg dem i smør i ca. 10 min.",
        "Server på rugbrød med remoulade og citron."],
       ["klassiker"]),
    _r("gnocchi", "Gnocchi med tomat og mozzarella", "Bagt gnocchi i tomatsovs med basilikum.",
       25, "vegetar", "🍅",
       [("gnocchi", 1000, "g"), ("hakkede tomater", 2, "dåse"), ("mozzarella", 2, "stk"), ("basilikum", 1, "stk"),
        ("hvidløg", 2, "fed"), ("parmesan", 50, "g"), ("olivenolie", 2, "spsk", P)],
       ["Lav en hurtig sovs af hvidløg og tomater.", "Vend gnocchi i sovsen i et fad.",
        "Top med mozzarella og parmesan. Bag 15 min ved 220 °C.", "Drys med basilikum."],
       ["vegetar", "hurtig", "børnevenlig"]),
    _r("boller-i-karry", "Boller i karry", "Dansk klassiker med kødboller, karrysovs og ris.",
       50, "svin", "🍛",
       [("hakket svinekød", 500, "g"), ("æg", 1, "stk"), ("løg", 2, "stk"), ("æble", 1, "stk"),
        ("ris", 300, "g"), ("piskefløde", 1, "dl"), ("karry", 2, "spsk", P), ("hvedemel", 4, "spsk", P),
        ("smør", 40, "g"), ("hønsebouillon", 1, "stk", P)],
       ["Rør farsen med æg og mel. Kog bollerne i bouillon i 8 min.", "Lav karrysovs af smør, løg, karry og mel.",
        "Spæd op med bouillon og fløde. Tilsæt æble.", "Kom bollerne i. Server med ris."],
       ["klassiker", "børnevenlig"]),
]

BY_ID = {r.id: r for r in RECIPES}


def recipe_from_url(url: str) -> Recipe:
    """Importér en opskrift fra en webside (fx valdemarsro.dk, arla.dk)."""
    from nemlig_shopper.recipe_parser import parse_recipe_url

    parsed = parse_recipe_url(url)
    ingredients = [
        Ingredient(name=i.name, amount=i.quantity, unit=i.unit or "", pantry=_is_pantry(i.name))
        for i in parsed.ingredients
        if i.name
    ]
    rid = "url-" + hashlib.sha1(url.encode()).hexdigest()[:10]
    return Recipe(
        id=rid,
        title=parsed.title or "Importeret opskrift",
        description=url,
        minutes=0,
        main="andet",
        servings=parsed.servings or 4,
        ingredients=ingredients,
        source_url=url,
        emoji="🔗",
    )


PANTRY_WORDS = {
    "salt", "peber", "olie", "olivenolie", "rapsolie", "sukker", "mel", "hvedemel", "eddike",
    "bouillon", "karry", "paprika", "spidskommen", "oregano", "kanel", "vand", "chiliflager",
}


def _is_pantry(name: str) -> bool:
    words = set(name.lower().replace(",", " ").split())
    return bool(words & PANTRY_WORDS) or any(w.endswith("bouillon") for w in words)
