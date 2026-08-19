"""
Lastkombinationer enligt BFS 2024:6, 3 kap.

BFS 2024:6 UPPHAVDE EKS (BFS 2011:10 med andringar); overgangstiden gick
ut 2026-06-30. Sedan 2026-07-01 galler den ensam. Den har alltsa INTE
EN 1990:s 6.10a/6.10b utan tva egna kombinationer i tab. 3:1:

  LK1  gamma_d*1,2*Gk  + gamma_d*1,5*Qk (huvudlast)
                       + gamma_d*1,5*Psi0*Qk (ovriga)
  LK2  gamma_d*1,35*Gk                      (INGEN variabel last)

Gynnsam permanent last ar Gk i bada -- utan gamma_d.

Talen ligger i input/regelverk/bfs2024-6.toml, inte har. Forfattningstext
ar fri enligt 9 § upphovsrattslagen, sa de far aterges med paragraf- och
tabellnummer.
"""

from dataclasses import dataclass, field

import material

# Lastvaraktighet -> anvands for att valja k_mod
VARAKTIGHET = {
    "egentyngd": "permanent",
    "sno": "medel",       # EKS: snolast rakans som medellang i Sverige
    "vind": "momentan",
    "nyttig": "medel",
}


@dataclass
class Last:
    namn: str
    typ: str              # 'egentyngd' | 'sno' | 'vind' | 'nyttig'
    varde: float          # karakteristiskt, kN/m


@dataclass
class Kombination:
    namn: str
    faktorer: dict = field(default_factory=dict)   # {lastnamn: faktor}
    ledande: str = ""

    @property
    def k_mod_varaktighet(self) -> str:
        """Kortast forekommande varaktighet bland ingaende laster styr k_mod."""
        ordning = ["permanent", "lang", "medel", "kort", "momentan"]
        forekommer = [VARAKTIGHET[t] for t in self._typer if t]
        return max(forekommer, key=ordning.index) if forekommer else "permanent"


def psi_for(lasttyp: str, S_0: float = 3.0) -> dict:
    """Hela psi-raden for en lasttyp, BFS 2024:6 tab. 3:5/3:6."""
    if lasttyp == "sno":
        return material.psi_sno(S_0)
    if lasttyp == "vind":
        return material.psi("vind")
    if lasttyp == "nyttig":
        return material.psi("H")
    return {"psi0": 0.0, "psi1": 0.0, "psi2": 0.0}


def psi0(last: Last, s_k: float = 3.0) -> float:
    return psi_for(last.typ, s_k)["psi0"]


def brottgrans(laster: list, sakerhetsklass: int = 3,
               s_k: float = 3.0) -> list:
    """
    Lastkombinationer i brottgranstillstand, BFS 2024:6 tab. 3:1.

    Forfattningen har BARA TVA kombinationer -- inte EN 1990:s 6.10a och
    6.10b:

      LK1  gamma_d*1,2*Gk + gamma_d*1,5*Qk (huvudlast)
                          + gamma_d*1,5*Psi0*Qk (ovriga)
      LK2  gamma_d*1,35*Gk                      (ingen variabel last)

    LK1 provas med VARJE variabel last som huvudlast. LK2 maste provas
    separat trots mindre lasteffekt, for k_mod bestams av kombinationens
    kortaste varaktighet (EN 1995-1-1 3.1.3(2)): utan snon blir k_mod
    0,60 i stallet for 0,80, alltsa 25 % lagre kapacitet. Gransen ligger
    vid snolast ungefar 0,375 gangerimatt egentyngden.

    Dessutom byggs lyftfallet: gynnsam permanent last ar enligt tab. 3:1
    Gk RAKT AV, utan gamma_d -- gamma_d galler bara ogynnsam last.

    Returnerar lista av (namn, {lastnamn: faktor}, ledande_typ).
    """
    g_d = material.gamma_d(sakerhetsklass)
    lk = material.lastkombinationer()
    perm = [l for l in laster if l.typ == "egentyngd"]
    var = [l for l in laster if l.typ != "egentyngd"]

    kombos = []

    # LK2 -- enbart permanent last
    lk2 = lk["LK2"]
    f = {l.namn: g_d * lk2["gamma_G_ogynnsam"] for l in perm}
    for l in var:
        f[l.namn] = 0.0
    kombos.append((f"BFS tab. 3:1 LK2 (endast permanent)", f, "permanent"))

    # LK1 -- varje variabel last som huvudlast
    lk1 = lk["LK1"]
    for ledande in var:
        f = {l.namn: g_d * lk1["gamma_G_ogynnsam"] for l in perm}
        for l in var:
            f[l.namn] = (g_d * lk1["gamma_Q"] if l is ledande
                         else g_d * lk1["gamma_Q"] * psi0(l, s_k))
        kombos.append((f"BFS tab. 3:1 LK1 ({ledande.namn} huvudlast)", f,
                       ledande.typ))

    # LK1 med GYNNSAM permanent last -- lyftfallet. Snon ar gynnsam nar
    # vinden lyfter och satts da till noll ("Variabel last, Q, gynnsam: 0").
    for l in [v for v in var if v.typ == "vind"]:
        f = {p.namn: lk1["gamma_G_gynnsam"] for p in perm}
        for v in var:
            f[v.namn] = g_d * lk1["gamma_Q"] if v is l else 0.0
        kombos.append((f"BFS tab. 3:1 LK1 ({l.namn} huvudlast, gynnsam G)",
                       f, "vind"))

    return kombos


def varaktighet_for_kombination(faktorer: dict, laster: list) -> str:
    """
    Lastvaraktigheten som styr k_mod for en kombination: den KORTASTE
    bland de laster som ingar med faktor > 0, EN 1995-1-1 3.1.3(2).

    En kombination med vind (momentan) far alltsa k_mod for momentan last
    aven om snon dominerar i storlek.
    """
    ordning = ["permanent", "lang", "medel", "kort", "momentan"]
    typer = [l.typ for l in laster if faktorer.get(l.namn, 0.0) > 0.0]
    forekommer = [VARAKTIGHET.get(t, "permanent") for t in typer]
    return max(forekommer, key=ordning.index) if forekommer else "permanent"


def bruksgrans(laster: list, s_k: float = 3.0) -> list:
    """Karakteristisk och kvasipermanent kombination."""
    perm = {l.namn: 1.0 for l in laster if l.typ == "egentyngd"}
    var = [l for l in laster if l.typ != "egentyngd"]

    kombos = []
    for ledande in var:
        f = dict(perm)
        for l in var:
            f[l.namn] = 1.0 if l is ledande else psi0(l, s_k)
        kombos.append((f"SLS karakteristisk ({ledande.namn})", f))

    f = dict(perm)
    for l in var:
        f[l.namn] = PSI.get(l.typ, {"psi2": 0.0})["psi2"]
    kombos.append(("SLS kvasipermanent", f))
    return kombos
