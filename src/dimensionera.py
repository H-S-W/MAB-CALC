"""
Tomt falt = foresla.

Lamnas balken tom i projektfilen ("balk = \"\"") soker programmet igenom
biblioteket och redovisar ALLA kandidater med sina utnyttjanden -- inte
bara vinnaren. En optimering som bara spottar ur sig ett namn doljer hur
nara de andra lag och vad som falde dem.

Regeln: LAGSTA BALKHOJD som klarar balk-, forbands- och
nedbojningskontrollerna, darefter MINSTA SPIKANTAL i nockforbandet.
UPPLAGET redovisas per kandidat men styr inte valet: dess kapacitet
foljer serien och upplagsdetaljen (L1, forstarkning), inte balkhojden,
sa ratt atgard ar en annan upplagsdetalj -- inte en annan balk.
Anvandarbeslut 2026-08-18.

Skivhojderna foljer balken nar de ocksa lamnas tomma (0): livforstarkningen
far balkens fria livhojd och den utanpaliggande skivan balkhojden, precis
som i handbokens exempel.

Spiksokningen halier snittkrafterna fran den valda balkens korning fasta.
Det ar en andra ordningens forenkling: fler spikar ger nagot hogre K_r och
darmed nagot hogre nockmoment, men effekten pa momentet ar liten mot
effekten pa kapaciteten. Den valda konfigurationen verifieras till sist
med en full korning, sa forenklingen kan inte ge ett falskt godkannande.
"""

import copy
from dataclasses import dataclass, field

import berakning
import material
from forband import kontrollera


@dataclass
class Kandidat:
    namn: str
    h: float
    serie: str
    liv: str
    balk_u: float
    forband_u: float
    upplag_u: float
    nedbojning_u: float
    haller: bool
    styrande: str
    varningar: int = 0


@dataclass
class Forslag:
    kandidater: list
    vald: str = ""                      # "" = ingen kandidat haller
    spik: dict = field(default_factory=dict)
    resultat: object = None             # berakning.Resultat for valet
    anmarkningar: list = field(default_factory=list)


def _med_balk(cfg, namn):
    c = copy.deepcopy(cfg)
    c["geometri"]["balk"] = namn
    b = material.balk(namn)
    if not c["forband"].get("skiva_hojd_liv"):
        c["forband"]["skiva_hojd_liv"] = b.h_liv
    if not c["forband"].get("skiva_hojd_ytter"):
        c["forband"]["skiva_hojd_ytter"] = float(b.h)
    return c


def _kandidatlista(cfg):
    d = cfg.get("dimensionering", {})
    serie = d.get("foresla_serie", "") or None
    liv = d.get("foresla_liv", "") or None
    balkar = material.balkar(liv=liv, serie=serie)
    return sorted(balkar, key=lambda b: (b.h, b.serie, b.liv))


def foresla_balk(cfg) -> Forslag:
    """
    Provar varje kandidat i stigande hojdordning med HELA kedjan och
    valjer den lagsta som klarar balk, forband och nedbojning. Upplaget
    raknas och redovisas per kandidat men avgor inte valet.
    """
    kandidater, vald, res_vald = [], "", None
    anm = []
    lista = _kandidatlista(cfg)
    if not lista:
        raise ValueError("inga balkar matchar foresla_serie/foresla_liv")
    d = cfg.get("dimensionering", {})
    if not d.get("foresla_serie") and not d.get("foresla_liv"):
        anm.append(f"Ingen serie eller livtyp angiven: alla "
                   f"{len(lista)} balkar provas. Sätt foresla_serie/"
                   f"foresla_liv i [dimensionering] för en snabbare "
                   f"sökning.")

    for b in lista:
        res = berakning.kor(_med_balk(cfg, b.namn))
        u = {"balken": res.varsta_balkkontroll.utnyttjande,
             "nockförbandet": res.forband_utnyttjande,
             "nedböjningen": max((k.utnyttjande
                                  for k in res.nedbojning.kontroller),
                                 default=0.0)}
        styrande = max(u, key=u.get)
        kandidater.append(Kandidat(
            namn=b.namn, h=b.h, serie=b.serie, liv=b.liv,
            balk_u=u["balken"], forband_u=u["nockförbandet"],
            upplag_u=res.upplag_utnyttjande,
            nedbojning_u=u["nedböjningen"],
            haller=res.haller, styrande=styrande,
            varningar=len(res.varningar)))
        if res.haller and not vald:
            vald, res_vald = b.namn, res

    if not vald:
        anm.append("Ingen balk i urvalet klarar balk-, förbands- och "
                   "nedböjningskontrollerna. Se den styrande kolumnen: "
                   "är det nedböjningen kan överhöjd eller styvare serie "
                   "(HI/HB) behövas; är det balken hjälper högre balk.")
    if vald and res_vald.upplag_utnyttjande > 1.0:
        anm.append(f"Upplaget överskrids för {vald} (utnyttjande "
                   f"{res_vald.upplag_utnyttjande:.2f}) men styr inte "
                   f"valet: öka upplagslängden L1 eller förstärk livet "
                   f"vid stödet.")
    return Forslag(kandidater=kandidater, vald=vald, resultat=res_vald,
                   anmarkningar=anm)


def _ledad_utnyttjande(cfg, res, grupper, skiva, kmod_f, kmod_sk,
                       gamma_skiva):
    """Det LEDADE forbandets utnyttjande for res dimensionerande snitt."""
    from forband import ledad_nock
    fb = cfg["forband"]
    d = res.dimensionerande
    liv = grupper[1]
    led = ledad_nock(
        d.N, d.V, fb["kolumner_liv"], fb["rader_liv"], fb["cc_forbindare"],
        liv.kapacitet.F_v_Rk_kN * kmod_f / material.GAMMA_M_FORBAND,
        liv.n_snitt, fb["skiva_t"], fb["skiva_hojd_liv"],
        skiva.draghallfasthet() if skiva.har_draghallfasthet
        else skiva.bojhallfasthet(),
        skiva.skivskjuvhallfasthet(), kmod_sk, gamma_skiva,
        taklutning_grader=cfg["geometri"]["taklutning"],
        kant_ande=15.0 * liv.forbindare.d,
        forskjut_sida=float(fb.get("sidoforskjutning", 0.0))
        * fb["cc_forbindare"],
        bas_andel=float(fb.get("rutnat_bas", 0.5)),
        ankare=((res.balk.h / 2)
                * __import__("math").tan(
                    __import__("math").radians(
                        cfg["geometri"]["taklutning"]))
                if fb.get("rutnat_ankare", "") == "flansvinkel"
                else None))
    return led.utnyttjande


def foresla_spik(cfg, res) -> list:
    """
    Alla spikningar i nockforbandet som klarar de snittkrafter som res
    raknade fram, sorterade i stigande totalt antal (darefter stigande
    utnyttjande). Radantalet begransas av vad skivhojderna rymmer med det
    angivna c/c-avstandet.

    Att listan -- inte bara vinnaren -- returneras ar poangen: sokningen
    haller snittkrafterna FASTA, men fler spikar ger hogre K_r och darmed
    nagot hogre nockmoment. foresla() verifierar darfor kandidaterna i
    ordning med hela kedjan och tar den forsta som haller aven da.
    """
    fb = cfg["forband"]
    s = fb["cc_forbindare"]
    d = res.dimensionerande
    M, N, V = d.M, abs(d.N), d.V
    # Kontakt i foget maste raknas likadant som i berakning.kor, annars
    # sallar sokningen bort spikningar som kedjan hade godkant.
    N_kontakt = (0.5 * N if fb.get("kontakt_i_foget", False) and d.N < 0
                 else 0.0)
    kmod_f = berakning.k_mod_forband(res.skivmaterial.nyckel,
                                     cfg["projekt"]["klimatklass"],
                                     d.varaktighet)
    # Skivans egna kontroller far skivans EGET k_mod -- sqrt-mixen
    # (kmod_f) galler bara forbindarkapaciteten i forbandet.
    kmod_sk = material.k_mod_skiva(res.skivmaterial.nyckel,
                                   cfg["projekt"]["klimatklass"],
                                   d.varaktighet)
    gamma_forb = material.GAMMA_M_FORBAND
    gamma_skiva = material.gamma_M_skiva(res.skivmaterial.nyckel)

    # AXLARNA: forband.rutnat lagger forsta argumentet i x-led, och x ar
    # TVARS balken (flansgruppen sitter pa +/- c_flans/2, dvs
    # flanstyngdpunkterna). Det ar alltsa KOLUMNERNA som begransas av
    # skivhojden -- raderna loper langs balken, och skivans langd langs
    # balken finns inte i modellen. Forr begransades raderna av
    # skivhojden och kolumnerna inte alls, vilket lat sokningen lagga
    # livspikar utanfor livforstarkningen och rakna dem i I_p och N_Rd.
    ledad = not cfg.get("system", {}).get("nock_styv", True)
    skarvmetod = fb.get("nockmetod", "handbok") == "halvgrupp"
    max_kolumner_liv = max(1, berakning.ryms_i_skivhojd(
        fb["skiva_hojd_liv"], s))
    max_rader_flans = 40      # langs balken: ingen modellerad grans
    max_rader_liv = 40

    # En andra flanskolumn (zigzag, handboken s. 284) provas bara om den
    # ryms enligt tab. 8.2 -- sokningen ska inte foresla en geometri som
    # berakningen varnar for.
    ff = material.forbindare(fb["forbindare_flans"])
    rho_fl = material.flanskvaliteter()[
        fb.get("flanskvalitet", "C30plus")]["rho_k"]
    b = material.balk(cfg["geometri"]["balk"])
    max_kf = 2 if not berakning.flanskolumner(ff, b.h_flans, 2,
                                              rho_fl)[1] else 1

    # Spikmonstret ingar i optimeringen (2026-08-19): bada monstren
    # provas per geometri, och sorteringen pa (totalt, utnyttjande)
    # later handbokens ram (fig. 5.30) vinna dar den racker med farre
    # spik. "kant" skiljer sig fran rutnatet forst nar det finns inre
    # kolumner att glesa ur (kl >= 3) och fler rader an andblocket --
    # annars vore kandidaten en dubblett av rutnatet. Den LEDADE
    # nocken har sin egen spikbild (5.3.7) som monstret inte galler.
    andblock = int(fb.get("rader_andblock", 3))
    monsterval = ("rutnat",) if ledad else ("rutnat", "kant")
    passande = []
    for rf in range(2, max_rader_flans + 1):
        for kl in range(2, max_kolumner_liv + 1):
            for rl in range(2, max_rader_liv + 1):
              for kf in range(1, max_kf + 1):
               for monster in monsterval:
                if monster == "kant" and (kl < 3 or rl <= andblock):
                    continue
                c = copy.deepcopy(cfg)
                c["forband"].update(rader_flans=rf, kolumner_flans=kf,
                                    kolumner_liv=kl, rader_liv=rl,
                                    spikmonster=monster,
                                    rader_andblock=andblock)
                grupper, skiva, _ = berakning.spikgrupper(
                    material.balk(c["geometri"]["balk"]), c["forband"],
                    c["forband"].get("flanskvalitet", "C30plus"),
                    c["geometri"]["taklutning"])
                # totalt raknas ur de BYGGDA grupperna, sa att det
                # stammer aven for kantmonstret (som glesar ur mitten)
                totalt = sum(gr.antal for gr in grupper)
                if passande and totalt > max(p["totalt"]
                                             for p in passande) + 200:
                    continue
                skalade = berakning.skala_grupper(grupper, kmod_f,
                                                  gamma_forb)
                sk_hb, sk_pl = berakning._skivsatser(c["forband"], skiva,
                                                     kmod_sk, gamma_skiva)
                skivor = sk_pl if sk_pl is not None else sk_hb
                # Sallningen maste anvanda SAMMA storhet som kedjan
                # bedomer forbandet med -- annars foreslas en spikning
                # som den fulla korningen underkanner (eller tvartom).
                if ledad:
                    u = _ledad_utnyttjande(c, res, grupper, skiva, kmod_f,
                                           kmod_sk, gamma_skiva)
                else:
                    u = kontrollera(skivor, [g for _, g, _ in skalade],
                                    M, N, V, N_kontakt,
                                    skarv=skarvmetod).utnyttjande_totalt
                if u <= 1.0:
                    passande.append(dict(rader_flans=rf, kolumner_flans=kf,
                                         kolumner_liv=kl, rader_liv=rl,
                                         spikmonster=monster,
                                         rader_andblock=andblock,
                                         totalt=totalt, utnyttjande=u))
    return sorted(passande,
                  key=lambda sp: (sp["totalt"], sp["utnyttjande"]))


MAX_VERIFIERINGAR = 8


def foresla(cfg) -> Forslag:
    """
    Hela forslaget: balk forst, sedan minsta spikning pa den valda.

    Spikkandidaterna provas i stigande antal och den forsta som haller i
    en FULL verifieringskorning valjs -- den fasta snittkrafts-
    forenklingen i foresla_spik kan alltsa inte ge ett falskt
    godkannande, och underkanner K_r-aterkopplingen minsta kandidaten
    gar sokningen vidare till nasta i stallet for att ge upp.
    """
    forslag = foresla_balk(cfg)
    if not forslag.vald:
        return forslag

    c0 = _med_balk(cfg, forslag.vald)
    kandidater = foresla_spik(c0, forslag.resultat)
    if not kandidater:
        forslag.spik = dict(
            hittad=False,
            kommentar="Ingen spikning inom skivhöjderna räcker. Högre "
                      "balk, större skivor eller grövre förbindare krävs.")
        return forslag

    for spik in kandidater[:MAX_VERIFIERINGAR]:
        c = copy.deepcopy(c0)
        c["forband"].update(rader_flans=spik["rader_flans"],
                            kolumner_flans=spik.get("kolumner_flans", 1),
                            kolumner_liv=spik["kolumner_liv"],
                            rader_liv=spik["rader_liv"],
                            spikmonster=spik.get("spikmonster", "rutnat"),
                            rader_andblock=spik.get("rader_andblock", 3))
        verifiering = berakning.kor(c)
        spik["utnyttjande_verifierad"] = verifiering.forband_utnyttjande
        spik["verifierad"] = verifiering.forband_utnyttjande <= 1.0
        if spik["verifierad"]:
            forslag.spik = dict(spik, hittad=True)
            break
    else:
        forslag.spik = dict(kandidater[0], hittad=False, verifierad=False,
                            kommentar=f"Ingen av de "
                            f"{min(len(kandidater), MAX_VERIFIERINGAR)} "
                            f"minsta spikningarna höll i den fulla "
                            f"verifieringen (K_r-återkopplingen). Den "
                            f"minsta redovisas nedan med sitt verifierade "
                            f"utnyttjande -- utöka spikningen.")
        forslag.anmarkningar.append(forslag.spik["kommentar"])
    return forslag
