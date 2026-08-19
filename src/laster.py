"""
Laster pa sadeltak.

Referenser:
  EN 1991-1-1        egentyngd och nyttig last
  EN 1991-1-3 + EKS  snolast
  EN 1991-1-4 + EKS  vindlast

Alla returnerade laster ar KARAKTERISTISKA och anges som last per
kvadratmeter HORISONTALPROJEKTION dar inget annat anges - det ar sa
snolasten definieras, och det gor kombinationen enklare.
"""

from dataclasses import dataclass

import material
from math import cos, log, radians


# ---------------------------------------------------------------------------
# Egentyngd
# ---------------------------------------------------------------------------

def egentyngd(skikt: dict, lutning_grader: float) -> float:
    """
    skikt: {'benamning': tyngd i kN/m2 av TAKYTA}
    Returnerar egentyngd per m2 horisontalprojektion.
    """
    g_takyta = sum(skikt.values())
    return g_takyta / cos(radians(lutning_grader))


# ---------------------------------------------------------------------------
# Snolast, EN 1991-1-3 avsnitt 5.3.3 (sadeltak)
# ---------------------------------------------------------------------------

def mu1(alpha: float) -> float:
    """Formfaktor for snolast, EN 1991-1-3 tab. 5.2 (ingen snorasskydd)."""
    if alpha <= 30.0:
        return 0.8
    if alpha < 60.0:
        return 0.8 * (60.0 - alpha) / 30.0
    return 0.0


@dataclass
class Snolastfall:
    namn: str
    s_vanster: float      # kN/m2 horisontalprojektion
    s_hoger: float


def snolast(s_k: float, alpha: float, C_e: float = 1.0,
            C_t: float = 1.0) -> list:
    """
    Returnerar de tre lastfallen enligt EN 1991-1-3 fig. 5.3 for sadeltak.

    s_k  karakteristisk snolast pa mark [kN/m2], enligt EKS karta
    alpha  taklutning [grader]
    C_e  exponeringsfaktor (1.0 normal, 0.8 vindutsatt, 1.2 skyddad)
    C_t  termisk koefficient (normalt 1.0)

    Lastfall (ii) och (iii) ar de osymmetriska. De ar nastan alltid
    dimensionerande for momentet i en momentstyv nock - hoppa inte over dem.
    """
    m = mu1(alpha)
    s = m * C_e * C_t * s_k
    return [
        Snolastfall("(i) symmetrisk", s, s),
        Snolastfall("(ii) osymmetrisk vanster", s, 0.5 * s),
        Snolastfall("(iii) osymmetrisk hoger", 0.5 * s, s),
    ]


# ---------------------------------------------------------------------------
# Vindlast, EN 1991-1-4
#
# Hastighetstrycket q_p och formfaktorerna c_pe ar INDATA i projektfilen:
# q_p lases ur EKS tabell for terrangtyp och byggnadshojd, c_pe ur
# EN 1991-1-4 tab. 7.4a for taklutningen (med BADA tecknen dar tabellen ger
# tva). Modulen bygger lastfallen ur dem -- den innehaller inga
# tabellvarden, av samma skal som materialbiblioteken: varden som
# dimensionerar tak ska lasas ur kallan, inte ur nagons minne.
# ---------------------------------------------------------------------------

@dataclass
class Vindfall:
    """
    Nettotryck vinkelratt MOT takytan [kN/m2 TAKYTA], positivt = tryck
    mot ytan (in mot huset), negativt = sug.

    w_lov  pa lovartsidan (dar vinden blaser pa)
    w_la   pa lasidan
    spegel True nar fallet ar speglat sa att hoger sida ar lovart
    """
    namn: str
    w_lov: float
    w_la: float
    spegel: bool = False

    @property
    def w_vanster(self):
        return self.w_la if self.spegel else self.w_lov

    @property
    def w_hoger(self):
        return self.w_lov if self.spegel else self.w_la


def vindfall(q_p: float, c_pe_lov: list, c_pe_la: list,
             c_pi: list) -> list:
    """
    Bygger alla vindlastfall som produkten av formfaktorerna:

        w = q_p * (c_pe - c_pi)      EN 1991-1-4 5.2, netto pa ytan

    c_pe_lov  formfaktorer for lovartsidan, t.ex. [0.2, -0.9] -- tab. 7.4a
              ger BADA tecknen for lutningar kring 15-30 grader och bada
              ska provas
    c_pe_la   formfaktorer for lasidan
    c_pi      inre tryck, [0.2, -0.3] nar oppningarna inte ar kanda
              (EN 1991-1-4 7.2.9(6) not 2)

    Varje kombination speglas ocksa, sa att vind fran bada hallen provas.
    Antalet fall ar alltsa 2 * len(lov) * len(la) * len(pi).
    """
    fall = []
    for ce_lov in c_pe_lov:
        for ce_la in c_pe_la:
            for ci in c_pi:
                namn = f"cpe {ce_lov:+.2f}/{ce_la:+.2f} cpi {ci:+.1f}"
                w_lov = q_p * (ce_lov - ci)
                w_la = q_p * (ce_la - ci)
                fall.append(Vindfall(f"vind v->h {namn}", w_lov, w_la))
                fall.append(Vindfall(f"vind h->v {namn}", w_lov, w_la,
                                     spegel=True))
    return fall


# ---------------------------------------------------------------------------
# Omvandling till linjelast pa en takstol
# ---------------------------------------------------------------------------

def linjelast(q_m2: float, cc: float) -> float:
    """kN/m2 -> kN/m pa en takstol med c/c-avstand cc [m]."""
    return q_m2 * cc


# ---------------------------------------------------------------------------
# Vindens hastighetstryck, BFS 2024:6 4 kap. 38-39 §
# ---------------------------------------------------------------------------

def q_pk(v_b, terrangtyp, z, c_0=1.0):
    """
    Karakteristiskt hastighetstryck [kN/m2] enligt BFS 2024:6 4 kap. 38 §:

        q_pk(z) = [1 + 2*k_p*I_v(z)] * [k_r*ln(z/z0)*c_0(z)]^2 * q_b
        I_v(z)  = 1 / (c_0(z)*ln(z/z0))
        k_r     = 0,19*(z0/z0_ref)^0,07
        q_b     = 0,5*rho*v_b^2

    For z < z_min galler q_pk(z) = q_pk(z_min) -- vindtrycket ar konstant
    darunder.

    v_b          referensvindhastighet [m/s], 35 § (Boverkets figur 4:3
                 eller API:et)
    terrangtyp   "0", "I", "II", "III" eller "IV", tab. 4:4. INGET
                 forval -- valet ar en platsbedomning.
    z            referenshojd [m]
    c_0          topografifaktor. 1,0 om topografin inte behover beaktas;
                 den bedomningen ar konstruktorens.

    OBS att spetsfaktorn k_p = 3,0 bara galler nar hansyn till
    egenfrekvens inte behover beaktas (38 §). For barverk dar dynamiska
    effekter har vasentlig paverkan ska den raknas separat.
    """
    if v_b <= 0:
        raise ValueError("v_b maste vara > 0")
    if c_0 <= 0:
        raise ValueError("c_0 maste vara > 0")
    t = material.terrang(terrangtyp)
    k = material.vindkonstanter()
    z0, z_min = t["z0"], t["z_min"]
    z_ef = max(float(z), z_min)

    k_r = 0.19 * (z0 / k["z0_ref"]) ** 0.07
    ln_z = log(z_ef / z0)
    I_v = 1.0 / (c_0 * ln_z)
    q_b = 0.5 * k["rho"] * v_b ** 2                 # Pa
    q = (1 + 2 * k["k_p"] * I_v) * (k_r * ln_z * c_0) ** 2 * q_b
    return q / 1000.0                               # Pa -> kN/m2
