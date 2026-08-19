"""
Balkens egen barformaga i brottgranstillstand.

ETA 12/0018 ger KARAKTERISTISKA kapaciteter i tab. 11 och 12. Den ger daremot
INTE partialkoefficienten gamma_M -- det ar ett nationellt val. Handboken
raknar med gamma_m = 1,3 i sitt eget exempel 5.2.2.1 (s. 232), tillsammans
med k_mod = 0,8, och det ar vardet projektet utgar fran. Se
[dimensionering] i input/projekt.toml, dar det gar att andra.

Att 1,3 ar rimligt stods av hur ETA:n sjalv delar upp k_mod i tab. 17:
bojningens rad, 0,60/0,70/0,80/0,90/1,10, ar EC5 tab. 3.1:s rad for
MASSIVT TRA, medan tvarkraftens rader ar skivmaterialens. ETA:n behandlar
alltsa bojning som ett flansbrott i tra -- och gamma_M for massivt tra ar
1,3 enligt EC5 tab. 2.3.

Referenser:
  ETA 12/0018 tab. 11/12   M_k, V_k, N_ck, N_tk, EI
  ETA 12/0018 tab. 17      k_mod, olika for bojning och tvarkraft
  ETA 12/0018 tab. 19      krav pa sidostod av tryckflansen
  EN 1995-1-1 6.2.3        kombinerad bojning och axiell DRAGKRAFT
  EN 1995-1-1 6.3.2        kombinerad bojning och axiell TRYCKKRAFT, k_c
  handboken s. 232         gamma_m = 1,3
"""

from dataclasses import dataclass, field
from math import pi, sqrt


# ---------------------------------------------------------------------------
# En enskild kontroll
# ---------------------------------------------------------------------------

@dataclass
class Kontroll:
    """
    namn         vad som kontrolleras
    E_d          dimensionerande lasteffekt
    R_d          dimensionerande barformaga, None for rena kvotkontroller
    enhet        enhet for E_d och R_d
    utnyttjande  E_d/R_d, eller interaktionsuttryckets varde
    referens     var kontrollen kommer fran
    formel       uttrycket som raknats, for redovisning
    """
    namn: str
    utnyttjande: float
    referens: str
    E_d: float = None
    R_d: float = None
    enhet: str = ""
    formel: str = ""
    anmarkningar: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.utnyttjande <= 1.0


# ---------------------------------------------------------------------------
# Dimensionerande barformagor
# ---------------------------------------------------------------------------

def M_Rd(balk, k_mod_bojning, gamma_M) -> float:
    """
    Dimensionerande momentkapacitet [kNm].

    M_k ur ETA tab. 11/12 innehaller redan storleksfaktorn k_h = (300/h)^0,25
    ur ekv. 1 -- den ska inte laggas till igen. Det ar verifierat i
    tests/test_eta_balkar.py, dar M_k raknas fram ur EI, f_m,k och k_h for
    alla 72 balkar.

    GALLER BARA om tryckflansen ar sidostodd enligt ETA tab. 19. Det provas
    separat, se sidostod_racker().
    """
    return balk.M_k * k_mod_bojning / gamma_M


def V_Rd(balk, k_mod_tvarkraft, gamma_M) -> float:
    """
    Dimensionerande tvarkraftskapacitet [kN].

    OBS att k_mod for tvarkraft ar en annan och lagre faktor an for bojning,
    ETA tab. 17, och att den beror pa livmaterialet. Det ar livet som bar
    tvarkraften.
    """
    return balk.V_k * k_mod_tvarkraft / gamma_M


def N_c_Rd(balk, k_mod_bojning, gamma_M) -> float:
    """Dimensionerande tryckkapacitet [kN], utan knackningsreduktion."""
    return balk.N_ck * k_mod_bojning / gamma_M


def N_t_Rd(balk, k_mod_bojning, gamma_M) -> float:
    """
    Dimensionerande dragkapacitet [kN].

    Hojer fel for HB-balkar med OSB-liv, dar ETA tab. 11 upprepar
    M_k-kolumnen i N_tk-kolumnen. Se docs/ERRATA.md punkt 4.
    """
    return balk.N_tk * k_mod_bojning / gamma_M


# ---------------------------------------------------------------------------
# Knackning i balkens plan
# ---------------------------------------------------------------------------

def N_crit(balk, L_ef, E05_kvot) -> float:
    """
    Eulers knacklast i balkens plan [kN].

        N_crit = pi^2 * EI_05 / L_ef^2

    EI ur ETA tab. 11 ar raknad med flansens MEDELELASTICITETSMODUL, tab. 5.
    EN 1995-1-1 6.3.2 kraver 5-percentilen E_0,05 for knackning. For massivt
    tra ar E_0,05 ca 2/3 av E_0,mean enligt EN 338, och flansarna star for
    narmare 90 % av styvheten -- se material.Balk.EA(). Kvoten anges darfor
    som en parameter, E05_kvot, med 0,67 som utgangsvarde.

    Det ar en HARLEDNING, inte en deklarerad storhet. Redovisa den.
    """
    return pi**2 * (balk.EI * E05_kvot) / L_ef**2


def lambda_rel(balk, L_ef, E05_kvot) -> float:
    """
    Relativt slankhetstal, EN 1995-1-1 6.3.2.

    Uttrycket i EC5 ar lambda_rel = (lambda/pi) * sqrt(f_c,0,k / E_0,05).
    Skrivet i kapaciteter i stallet for spanningar blir det

        lambda_rel = sqrt(N_ck / N_crit)

    eftersom f_c,0,k * A ar precis den karakteristiska tryckkapaciteten
    N_ck som ETA:n deklarerar. Det gor att inga ej deklarerade storheter
    som A eller f_c,0,k behover gissas.
    """
    return sqrt(balk.N_ck / N_crit(balk, L_ef, E05_kvot))


def k_c(lam_rel, beta_c=0.2) -> float:
    """
    Knackningsreduktionsfaktor, EN 1995-1-1 ekv. 6.25 och 6.27.

        k = 0,5 * (1 + beta_c*(lambda_rel - 0,3) + lambda_rel^2)
        k_c = 1 / (k + sqrt(k^2 - lambda_rel^2))

    beta_c = 0,2 for massivt tra, 0,1 for limtra och LVL (ekv. 6.29).
    Flansarna ar massivt tra, sa 0,2 ar det konsekventa valet.

    For lambda_rel <= 0,3 ar k_c = 1,0 och interaktionen kvadreras i
    stallet, se 6.3.2(3).
    """
    if lam_rel <= 0.3:
        return 1.0
    k = 0.5 * (1 + beta_c * (lam_rel - 0.3) + lam_rel**2)
    return 1.0 / (k + sqrt(k**2 - lam_rel**2))


# ---------------------------------------------------------------------------
# Sidostod
# ---------------------------------------------------------------------------

def sidostod_racker(balk, avstand_mm) -> bool:
    """
    ETA annex 3 tab. 19: den deklarerade momentkapaciteten galler bara nar
    TRYCKFLANSEN ar sidostodd med hogst sidostod_max.

    Villkoret ersatter en vippningsberakning -- men det maste provas mot den
    flans som faktiskt ar tryckt. Vid positivt moment ar det overflansen,
    dar taklakten sitter. Vid negativt moment ar det underflansen.
    """
    return 0 < avstand_mm <= balk.sidostod_max


# ---------------------------------------------------------------------------
# Samlad kontroll
# ---------------------------------------------------------------------------

def kontrollera(balk, M_Ed, V_Ed, N_Ed, L_ef, k_mod_bojning,
                k_mod_tvarkraft, gamma_M, beta_c=0.2, E05_kvot=0.67):
    """
    Kontrollerar balken i brottgranstillstand och returnerar en lista med
    Kontroll.

    M_Ed   dimensionerande moment [kNm], tecken spelar ingen roll har
    V_Ed   dimensionerande tvarkraft [kN]
    N_Ed   dimensionerande axialkraft [kN], POSITIV = DRAG, negativ = tryck
           (samma teckenkonvention som ram.internal())
    L_ef   knacklangd i balkens plan [m]

    Kontrollerna:
      bojning        M_Ed / M_Rd
      tvarkraft      V_Ed / V_Rd, med tvarkraftens egen k_mod
      axialkraft     N_Ed / N_Rd, tryck eller drag
      interaktion    EC5 6.2.3 vid drag, 6.3.2 vid tryck
    """
    ut = []
    M, V = abs(M_Ed), abs(V_Ed)
    M_d = M_Rd(balk, k_mod_bojning, gamma_M)
    V_d = V_Rd(balk, k_mod_tvarkraft, gamma_M)

    ut.append(Kontroll(
        namn="Bojning", E_d=M, R_d=M_d, enhet="kNm", utnyttjande=M / M_d,
        referens="ETA tab. 11/12 med k_mod ur tab. 17",
        formel=f"M_Ed/M_Rd = {M:.2f}/{M_d:.2f}"))

    ut.append(Kontroll(
        namn="Tvarkraft", E_d=V, R_d=V_d, enhet="kN", utnyttjande=V / V_d,
        referens=f"ETA ekv. 6/7, k_mod tvarkraft = {k_mod_tvarkraft} "
                 f"({balk.liv}-liv)",
        formel=f"V_Ed/V_Rd = {V:.2f}/{V_d:.2f}"))

    if N_Ed >= 0:
        ut.extend(_dragfall(balk, N_Ed, M, M_d, k_mod_bojning, gamma_M))
    else:
        ut.extend(_tryckfall(balk, -N_Ed, M, M_d, L_ef, k_mod_bojning,
                             gamma_M, beta_c, E05_kvot))
    return ut


def _dragfall(balk, N, M, M_d, k_mod, gamma_M):
    """Kombinerad bojning och axiell dragkraft, EN 1995-1-1 6.2.3."""
    if not balk.har_dragkapacitet:
        return [Kontroll(
            namn="Axialkraft, drag", utnyttjande=float("inf"),
            referens="docs/ERRATA.md punkt 4",
            formel="N_tk saknas i ETA tab. 11 for HB med OSB-liv",
            anmarkningar=[
                f"{balk.namn} dras men dragkapaciteten gar inte att slaa "
                f"upp: ETA tab. 11 upprepar M_k-kolumnen i N_tk-kolumnen "
                f"for HB-serien. Valj spanskiveliv ({balk.namn}s) eller en "
                f"annan serie, eller begar vardet fran Masonite Beams."])]

    N_d = N_t_Rd(balk, k_mod, gamma_M)
    return [
        Kontroll(namn="Axialkraft, drag", E_d=N, R_d=N_d, enhet="kN",
                 utnyttjande=N / N_d, referens="ETA tab. 11/12, N_tk",
                 formel=f"N_Ed/N_t,Rd = {N:.2f}/{N_d:.2f}"),
        Kontroll(namn="Bojning + drag", utnyttjande=N / N_d + M / M_d,
                 referens="EN 1995-1-1 6.2.3, ekv. 6.17",
                 formel=f"N_Ed/N_t,Rd + M_Ed/M_Rd = "
                        f"{N / N_d:.3f} + {M / M_d:.3f}")]


def _tryckfall(balk, N, M, M_d, L_ef, k_mod, gamma_M, beta_c, E05_kvot):
    """
    Kombinerad bojning och axiell tryckkraft, EN 1995-1-1 6.3.2.

    Knackning UR planet forutsatts forhindrad av sidostodet enligt ETA
    tab. 19. Det ar samma villkor som momentkapaciteten vilar pa, och det
    kontrolleras separat -- se sidostod_racker(). Bara knackning I planet
    raknas har.
    """
    N_d = N_c_Rd(balk, k_mod, gamma_M)
    lam = lambda_rel(balk, L_ef, E05_kvot)
    kc = k_c(lam, beta_c)
    Ncr = N_crit(balk, L_ef, E05_kvot)

    ut = [Kontroll(
        namn="Axialkraft, tryck", E_d=N, R_d=N_d, enhet="kN",
        utnyttjande=N / N_d, referens="ETA tab. 11/12, N_ck",
        formel=f"N_Ed/N_c,Rd = {N:.2f}/{N_d:.2f}")]

    if lam <= 0.3:
        ut.append(Kontroll(
            namn="Bojning + tryck", utnyttjande=(N / N_d)**2 + M / M_d,
            referens="EN 1995-1-1 6.3.2(3), ekv. 6.19",
            formel=f"(N_Ed/N_c,Rd)^2 + M_Ed/M_Rd = "
                   f"{(N / N_d)**2:.3f} + {M / M_d:.3f}",
            anmarkningar=[f"lambda_rel = {lam:.3f} <= 0,3, alltsa kort "
                          f"stang: ingen knackningsreduktion."]))
    else:
        ut.append(Kontroll(
            namn="Bojning + tryck med knackning",
            utnyttjande=N / (kc * N_d) + M / M_d,
            referens="EN 1995-1-1 6.3.2(3), ekv. 6.23",
            formel=f"N_Ed/(k_c*N_c,Rd) + M_Ed/M_Rd = "
                   f"{N / (kc * N_d):.3f} + {M / M_d:.3f}",
            anmarkningar=[
                f"lambda_rel = {lam:.3f}, k_c = {kc:.3f}, "
                f"N_crit = {Ncr:.1f} kN vid knacklangd {L_ef:.2f} m.",
                f"Knackning ur planet forutsatts forhindrad av sidostod "
                f"enligt ETA tab. 19, hogst {balk.sidostod_max:.0f} mm.",
                f"EI_05 = {E05_kvot:.2f}*EI ar HARLETT, se N_crit()."]))
    return ut


def varsta(kontroller) -> Kontroll:
    """Den kontroll som har hogst utnyttjande."""
    return max(kontroller, key=lambda k: k.utnyttjande)


def utnyttjande(balk, M_Ed, V_Ed, N_Ed, L_ef, k_mod_bojning,
                k_mod_tvarkraft, gamma_M, beta_c=0.2, E05_kvot=0.67) -> float:
    """
    Hogsta utnyttjandet i ett snitt, raknat utan att bygga Kontroll-objekt.

    Finns for att kunna skanna hundratals snitt langs sparrarna billigt.
    Ger samma tal som max(k.utnyttjande for k in kontrollera(...)) -- det
    finns ett test som jamfor de tva vagarna.
    """
    M, V = abs(M_Ed), abs(V_Ed)
    M_d = M_Rd(balk, k_mod_bojning, gamma_M)
    u = max(M / M_d, V / V_Rd(balk, k_mod_tvarkraft, gamma_M))

    if N_Ed >= 0:
        if not balk.har_dragkapacitet:
            return float("inf")
        N_d = N_t_Rd(balk, k_mod_bojning, gamma_M)
        return max(u, N_Ed / N_d, N_Ed / N_d + M / M_d)

    N = -N_Ed
    N_d = N_c_Rd(balk, k_mod_bojning, gamma_M)
    lam = lambda_rel(balk, L_ef, E05_kvot)
    if lam <= 0.3:
        interaktion = (N / N_d)**2 + M / M_d
    else:
        interaktion = N / (k_c(lam, beta_c) * N_d) + M / M_d
    return max(u, N / N_d, interaktion)


def utnyttjande_falt(balk, M, V, N, L_ef, k_mod_bojning, k_mod_tvarkraft,
                     gamma_M, beta_c=0.2, E05_kvot=0.67):
    """
    Vektoriserad utnyttjande() over numpy-faltar med M, V och N i samma
    punkter. Behovs for att skanna alla snitt i alla lastfall utan att
    Python-loopa -- kedjan provar hundratals fall.

    Ger exakt samma tal som utnyttjande() punkt for punkt; ett test jamfor.
    """
    import numpy as np

    M_, V_, N_ = np.abs(M), np.abs(V), np.asarray(N, dtype=float)
    M_d = M_Rd(balk, k_mod_bojning, gamma_M)
    V_d = V_Rd(balk, k_mod_tvarkraft, gamma_M)
    u = np.maximum(M_ / M_d, V_ / V_d)

    drag = N_ >= 0
    if drag.any():
        if not balk.har_dragkapacitet:
            u = np.where(drag, np.inf, u)
        else:
            N_t = N_t_Rd(balk, k_mod_bojning, gamma_M)
            u = np.maximum(u, np.where(drag, N_ / N_t + M_ / M_d, 0.0))

    tryck = ~drag
    if tryck.any():
        N_c = N_c_Rd(balk, k_mod_bojning, gamma_M)
        lam = lambda_rel(balk, L_ef, E05_kvot)
        Nn = np.where(tryck, -N_, 0.0)
        if lam <= 0.3:
            inter = (Nn / N_c) ** 2 + M_ / M_d
        else:
            inter = Nn / (k_c(lam, beta_c) * N_c) + M_ / M_d
        u = np.maximum(u, np.where(tryck, np.maximum(Nn / N_c, inter), 0.0))
    return u
