"""
Platsberoende lastforutsattningar ur Boverkets oppna API.

    S_0   karakteristiskt varde for snolast pa mark [kN/m2], BFS 2024:6
          4 kap. 30 §, figur 4:2
    v_b   referensvindhastighet [m/s], 35 §, figur 4:3

KARTORNA far inte aterges i projektet -- 9 § andra stycket punkt 1
upphovsrattslagen undantar kartor aven ur en i ovrigt fri forfattning.
Ett numeriskt varde for EN punkt ar daremot ett faktum, inte en kopia av
kartverket, och det ar precis vad API:et levererar.

LICENS. Datat ar INTE CC0. Boverkets anvandarvillkor (dnr 5913/2024)
tillater att man hamtar de varden ett projekt behover. Att skorda hela
landet till en offline-tabell i repot ar "annan anvandning" och kraver
skriftligt godkannande fran registraturen@boverket.se INNAN man borjar.
Den har modulen hamtar darfor per projekt, aldrig i bulk.

JURIDISK STATUS. Boverket anger sjalva att API-vardet ar VAGLEDNING: vid
avvikelse galler den tryckta utgavan av BFS 2024:6. Darfor lagras alltid
koordinat, apiversion och hamtdatum tillsammans med vardet, och
konstruktoren ska kunna kvittera det mot figur 4:2/4:3.

Modulen anropas ALDRIG fran berakning.kor. Den skriver in varden i
projektfilen; berakningen laser bara filen. Da ar en korning
reproducerbar utan natverk, och varje siffra har sin proveniens.
"""

from dataclasses import dataclass, field

import requests

API = "https://api.boverket.se/klimatlast/v2"
ANVANDARAGENT = "MasoniteBeams-takstol (lokal dimensionering)"

# SWEREF99 TM (EPSG:3006) tacker Sverige ungefar sa har. Kontrollen finns
# for att API:et ger SAMMA 404 for en felvand koordinat som for en punkt
# utanfor landet -- utan den gar felen inte att skilja at.
N_MIN, N_MAX = 6_100_000, 7_700_000      # sodra Skane -> Treriksroset
E_MIN, E_MAX = 200_000, 950_000

# 30 §: "Kartan ar giltig upp till 1 500 meter over havet."
HOH_MAX = 1500.0


class PlatsFel(Exception):
    """Uppslagningen gick inte att gora, eller far inte goras."""


@dataclass
class Platsdata:
    N: int                      # SWEREF99 TM northing
    E: int                      # SWEREF99 TM easting
    S_0: float                  # kN/m2
    v_b: float                  # m/s
    apiversion: str
    hamtat: str                 # ISO-datum
    hoh: float = 0.0
    spridning: dict = field(default_factory=dict)   # ringsamplingens utfall
    anmarkningar: list = field(default_factory=list)

    def som_toml(self) -> str:
        """Blocket som ska klistras in i input/projekt.toml."""
        rader = [
            "[plats]",
            f"x_koord = {self.N}       # N (northing), SWEREF99 TM",
            f"y_koord = {self.E}        # E (easting), SWEREF99 TM",
            f"hoh = {self.hoh}          # m över havet",
            "",
            "[plats.hamtat]",
            f'S_0 = {self.S_0}          # kN/m2, BFS 2024:6 4 kap. 30 §',
            f'v_b = {self.v_b}          # m/s,   BFS 2024:6 4 kap. 35 §',
            f'apiversion = "{self.apiversion}"',
            f'hamtat_datum = "{self.hamtat}"',
            'kalla = "Boverket, Klimatlaster. '
            'https://www.boverket.se/sv/om-boverket/oppna-data/'
            'klimatlaster-enligt-eks/"',
        ]
        return "\n".join(rader)


def _kontrollera_koordinat(N, E):
    if not (N_MIN <= N <= N_MAX and E_MIN <= E <= E_MAX):
        vand = E_MIN <= N <= E_MAX and N_MIN <= E <= N_MAX
        raise PlatsFel(
            f"N = {N}, E = {E} ligger utanför SWEREF99 TM:s svenska "
            f"omfång (N {N_MIN}-{N_MAX}, E {E_MIN}-{E_MAX})."
            + (" Koordinaterna ser OMVÄNDA ut -- API:ets 'x-koord' är "
               "northing och 'y-koord' är easting, tvärtemot namnen."
               if vand else ""))


def _fraga(endpoint, N, E, timeout=20):
    r = requests.get(f"{API}/{endpoint}",
                     params={"x-koord": int(N), "y-koord": int(E)},
                     headers={"User-Agent": ANVANDARAGENT}, timeout=timeout)
    if r.status_code == 404:
        raise PlatsFel(
            f"Boverket har inget värde för N {N}, E {E} ({endpoint}). "
            f"Punkten ligger utanför kartans täckning -- kontrollera att "
            f"den hamnar på land.")
    if r.status_code == 429:
        raise PlatsFel("Boverkets API begränsar anropstakten (429). "
                       "Vänta en stund och försök igen.")
    r.raise_for_status()
    d = r.json()
    # 'varde' ar en STRANG i svaret, och nyckeln innehaller a-ring.
    nyckel = next(k for k in d if k.lower().startswith("v"))
    return float(str(d[nyckel]).replace(",", ".")), d.get("apiversion", "?")


def hamta(N, E, hoh=0.0, datum=None, ring_m=2000.0, punkter=6,
          timeout=20) -> Platsdata:
    """
    Hamtar S_0 och v_b for en koordinat, och samplar en ring runt den for
    att upptacka att punkten ligger nara en zongrans.

    N, E     SWEREF99 TM. N = northing, E = easting.
    hoh      hojd over havet [m]. Over 1 500 m galler inte kartan (30 §)
             och uppslagningen vagrar -- da kravs egen statistisk analys
             enligt 31 §, mattserie med arsmaxima fran minst 30 ar.
    ring_m   radie for zongransprovningen. 0 stanger av den.
    datum    ISO-datum for hamtningen; maste anges av anroparen sa att
             modulen inte behover en klocka.
    """
    if datum is None:
        raise PlatsFel("datum måste anges (ISO-format) så att värdets "
                       "proveniens går att spåra")
    N, E = int(round(N)), int(round(E))
    _kontrollera_koordinat(N, E)
    if hoh > HOH_MAX:
        raise PlatsFel(
            f"Höjden {hoh:.0f} m över havet överstiger 1 500 m. Boverkets "
            f"karta gäller inte där (BFS 2024:6 4 kap. 30 §). Snölasten "
            f"måste bestämmas med egen statistisk analys enligt 31 §, "
            f"grundad på årsmaxima från minst 30 år.")

    S_0, ver = _fraga("snolast", N, E, timeout)
    v_b, _ = _fraga("vindlast", N, E, timeout)

    anm = []
    spridning = {}
    if ring_m > 0 and punkter > 0:
        from math import cos, pi, sin
        varden = [S_0]
        for i in range(punkter):
            a = 2 * pi * i / punkter
            try:
                v, _ = _fraga("snolast", N + ring_m * cos(a),
                              E + ring_m * sin(a), timeout)
                varden.append(v)
            except (PlatsFel, requests.RequestException):
                continue        # utanfor tackning eller strypt -- hoppa
        spridning = {"min": min(varden), "max": max(varden),
                     "radie_m": ring_m, "punkter": len(varden)}
        if spridning["max"] > S_0 + 1e-9:
            anm.append(
                f"Inom {ring_m:.0f} m från punkten finns snözoner upp till "
                f"{spridning['max']} kN/m2 mot punktens {S_0}. Byggnaden "
                f"ligger nära en zongräns -- överväg det högre värdet. "
                f"Valet är ditt, inte programmets.")

    anm.append(
        "Boverket anger att API-värdet är vägledning; vid avvikelse "
        "gäller den tryckta BFS 2024:6. Kvittera mot figur 4:2 och 4:3.")

    return Platsdata(N=N, E=E, S_0=S_0, v_b=v_b, apiversion=ver,
                     hamtat=datum, hoh=hoh, spridning=spridning,
                     anmarkningar=anm)
