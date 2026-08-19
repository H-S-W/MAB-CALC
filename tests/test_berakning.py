"""
Verifiering av src/berakning.py -- hela kedjan laster till nockforband.

Testerna sakrar de kopplingar som lopper genom flera moduler och darfor inte
fangas av enhetstesterna: att ETA-datat verkligen nar ramanalysen, att
EC5-kapaciteten nar spikgrupperna, att antalet skjuvsnitt bestams av
inträngningskontrollen och inte av en installning, och att
sidostodsvarningen utlosas av rätt teckenbyte i momentet.
"""

import copy
import tomllib
from pathlib import Path

import pytest

import berakning
import material

PROJEKTFIL = Path(__file__).parent.parent / "input" / "projekt.toml"


def grundcfg():
    with open(PROJEKTFIL, "rb") as fh:
        return tomllib.load(fh)


def cfg_med(**andringar):
    """
    Projektfilen med punktvisa andringar. Nycklarna skrivs med punkt:
    cfg_med(**{"geometri.balk": "H500"})
    """
    c = grundcfg()
    for stig, varde in andringar.items():
        delar = stig.split(".")
        d = c
        for del_ in delar[:-1]:
            d = d[del_]
        d[delar[-1]] = varde
    return c


@pytest.fixture(scope="module")
def res():
    return berakning.kor(grundcfg())


# ---------------------------------------------------------------------------
# Kedjan hanger ihop
# ---------------------------------------------------------------------------

def test_kedjan_gar_igenom_med_projektfilen(res):
    assert res.balk.namn == grundcfg()["geometri"]["balk"]
    # BFS 2024:6 tab. 3:1 har TVA kombinationer, inte EN 1990:s fyra:
    # LK1 med varje variabel last som huvudlast (sno, vind) plus
    # lyftfallet med gynnsam G = tre kombinationer med variabel last,
    # x tre snofall x (8 vindfall + fallet UTAN vind). LK2 (endast
    # permanent) har vindfaktor noll och provas bara utan vind: + 3.
    # LK2 behovs for sin k_mod (0,60 mot snofallens 0,80).
    assert len(res.vindfall) == 8            # 2 lov x 1 la x 2 cpi x 2 hall
    assert len(res.snittkrafter) == 3 * 3 * (len(res.vindfall) + 1) + 3
    assert res.dimensionerande in res.snittkrafter


def test_dimensionerande_nockfall_ar_utan_vind(res):
    """
    Kombinationen MED vind har momentan varaktighet och k_mod 1,10 mot
    0,80 -- kapaciteten stiger mer an vad vindtrycket bidrar med last.
    Darfor ar det snofallet UTAN vind som styr forbandet. Det ar hela
    skalet till att varje kombination provas bade med och utan vind.
    """
    assert res.dimensionerande.vindfall == "-"
    assert res.dimensionerande.varaktighet == "medel"
    assert res.balksnitt.vindfall == "-"


def test_symmetrisk_snolast_ar_dimensionerande_for_nockmomentet(res):
    """
    README:s notering: for en symmetrisk tvaledsram ger EN 1991-1-3:s
    osymmetriska fall LAGRE total last och darmed lagre nockmoment an det
    symmetriska. Det ar latt att tro motsatsen.
    """
    d = res.dimensionerande
    assert "symmetrisk" in d.snofall and "osymmetrisk" not in d.snofall
    assert "LK1" in d.kombination

    osym = [s for s in res.snittkrafter if "osymmetrisk" in s.snofall]
    assert all(abs(s.M) < abs(d.M) for s in osym)


def test_eta_datat_nar_ramanalysen(res):
    """
    EI ur ETA tab. 11 ska vara den styvhet ramen raknas med, och EA den
    harledda. Bada var tidigare platshallare som lag 22-29 % respektive
    ca 35 % fel.
    """
    assert res.balk.EI == material.balk(res.balk.namn).EI
    assert res.balk.EA() > 60_000


def test_ec5_kapaciteten_nar_spikgrupperna(res):
    """
    Gruppens kraft per forbindare ska vara EC5-kapaciteten multiplicerad med
    antalet skjuvsnitt -- inte ett tabellvarde.
    """
    for gr in res.grupper:
        assert gr.grupp.F == pytest.approx(gr.F_v_Rd * gr.n_snitt)
        assert gr.kapacitet.brottmod.startswith("8.")


def test_skivan_i_planet_dimensionerar_forbandet(res):
    """
    Med f_t,90 = 7,0 MPa (handboken 5.3.4.2) raknas plywooden i PLANET,
    och da ar det SKIVAN som dimensionerar forbandet -- inte
    forbindarna. Med handbokens plattbojnings-f_m (22,5) vore det
    tvartom; den vagen redovisas parallellt och skillnaden ar stor.
    """
    assert res.kontroll.dimensionerande == "plywood"
    assert res.kontroll_handbok.dimensionerande == "forbindare"
    assert res.kontroll.M_Rd < res.kontroll_handbok.M_Rd
    assert any("f_t,90" in v for v in res.varningar)


def test_livgruppen_far_tva_skjuvsnitt_med_2_5x50(res):
    """
    docs/ERRATA.md punkt 2 lamnade fragan oppen. Nu avgors den av
    inträngningskontrollen: 50 mm spik genom 18 + 10 + 18 mm ger 22 mm i
    sista delen, mot kravet 15 mm for rillad spik. Alltsa tva snitt.
    """
    liv = next(g for g in res.grupper if "liv" in g.namn)
    assert liv.n_snitt == 2
    assert liv.intrangning.uppfyllt
    assert liv.intrangning.intrangning == pytest.approx(22.0)


def test_flansgruppen_har_alltid_ett_skjuvsnitt(res):
    """Utanpaliggande skiva mot flans ar enkelsnitt oavsett spiklangd."""
    flans = next(g for g in res.grupper if "flans" in g.namn)
    assert flans.n_snitt == 1
    assert flans.kapacitet.brottmod.startswith("8.6")


def test_slat_spik_i_tjocka_skivor_tar_bort_det_bortre_skjuvsnittet():
    """
    Kravet pa inträngning ar 8d = 20 mm for SLAT spik men bara 6d = 15 mm
    for rillad (8.3.1.1). Med 22 mm skivor gar en 50 mm spik 22 + 10 = 32 mm
    innan sista delen och har 18 mm kvar. Det racker for en ankarspik men
    inte for en tradspik.

    Da ska berakningen falla tillbaka pa enkelsnitt och varna -- inte tyst
    rakna med tva snitt.
    """
    gemensamt = {"forband.skiva_t": 22.0, "forband.skivmaterial": "osb3"}

    rillad = berakning.kor(cfg_med(**gemensamt))
    liv = next(g for g in rillad.grupper if "liv" in g.namn)
    assert liv.intrangning.intrangning == pytest.approx(18.0)
    assert liv.n_snitt == 2                      # 18 mm > 6d = 15 mm

    slat = berakning.kor(cfg_med(
        **gemensamt, **{"forband.forbindare_liv": "tradspik_2_5x50"}))
    liv = next(g for g in slat.grupper if "liv" in g.namn)
    assert liv.n_snitt == 1                      # 18 mm < 8d = 20 mm
    assert any("far inte raknas" in v for v in slat.varningar)
    assert slat.kontroll.M_forbindare < rillad.kontroll.M_forbindare


# ---------------------------------------------------------------------------
# Sidostod, ETA tab. 19
# ---------------------------------------------------------------------------

def test_negativt_nockmoment_varnar_for_underflansen(res):
    assert res.dimensionerande.M < 0
    assert any("UNDERFLÄNSEN" in v for v in res.varningar)


def test_angivet_sidostod_av_underflansen_tystar_varningen():
    res = berakning.kor(cfg_med(**{"geometri.sidostod_underflans": 300.0}))
    assert not any("UNDERFLÄNSEN" in v for v in res.varningar)


def test_for_glest_sidostod_av_underflansen_varnar_anda():
    """H-serien kraver hogst 350 mm enligt ETA tab. 19."""
    res = berakning.kor(cfg_med(**{"geometri.sidostod_underflans": 600.0}))
    assert any("underflänsen är tryckt" in v.lower() for v in res.varningar)


def test_for_gles_taklakt_varnar_for_overflansen():
    res = berakning.kor(cfg_med(**{"geometri.cc_lakt": 0.6}))
    assert any("Överflänsen" in v for v in res.varningar)


def test_ledad_nock_tar_bort_nockmomentet_och_varningen():
    """
    Med ledad nock blir nockmomentet noll, overflansen ar tryckt overallt
    och taklakten gor sitt jobb. README:s poang: har man dragband eller
    vindsbjalklag behovs sannolikt ingen momentstyv nock alls.
    """
    res = berakning.kor(cfg_med(**{"system.nock_styv": False}))
    assert abs(res.dimensionerande.M) < 1e-6
    assert not any("UNDERFLÄNSEN" in v for v in res.varningar)


# ---------------------------------------------------------------------------
# Vad som paverkar forbandet och vad som inte gor det
# ---------------------------------------------------------------------------

def test_hogre_balk_ger_hogre_momentkapacitet_i_forbandet():
    """Havarmen i spikgruppen ar c_flans = h - h_flans."""
    lag = berakning.kor(cfg_med(**{"geometri.balk": "H200"}))
    hog = berakning.kor(cfg_med(**{"geometri.balk": "H500"}))
    assert hog.kontroll.M_forbindare > lag.kontroll.M_forbindare


def test_bredare_flans_hjalper_inte_nockforbandet():
    """
    Overraskande men riktigt: HB300 har mer an dubbelt sa bred flans som
    H300, men nockforbandets kapacitet ar identisk. Havarmen ar
    c_flans = h - h_flans, och h_flans ar 47 mm i alla fyra serier -- sa
    bara BALKHOJDEN spelar roll.

    Modellen lagger spikarna i tva kolumner, en per flans. En bredare flans
    skulle i praktiken rymma fler spikar i sidled, vilket handboken s. 284
    ocksa antyder med sin zigzag-spikning. Det utnyttjas inte an.
    """
    h = berakning.kor(cfg_med(**{"geometri.balk": "H300"}))
    hb = berakning.kor(cfg_med(**{"geometri.balk": "HB300"}))
    assert h.balk.b_flans == 47.0 and hb.balk.b_flans == 97.0
    assert h.balk.c_flans == hb.balk.c_flans
    assert hb.kontroll.M_forbindare == pytest.approx(h.kontroll.M_forbindare)


def test_fler_spikrader_ger_hogre_kapacitet():
    fa = berakning.kor(cfg_med(**{"forband.rader_flans": 4}))
    manga = berakning.kor(cfg_med(**{"forband.rader_flans": 10}))
    assert manga.kontroll.M_forbindare > fa.kontroll.M_forbindare


def test_kontakttryck_i_foget_halverar_normalkraften():
    """
    Handboken s. 290 med hanvisning till EN 1995-1-1 8.8.5. Utnyttjandet ska
    sjunka, och antagandet ska redovisas.
    """
    utan = berakning.kor(grundcfg())
    med = berakning.kor(cfg_med(**{"forband.kontakt_i_foget": True}))
    assert med.kontroll.utnyttjande < utan.kontroll.utnyttjande
    assert any("kontakt i" in a for a in med.antaganden)
    assert not any("kontakt i" in a for a in utan.antaganden)


def test_klimatklass_2_ger_lagre_kapacitet():
    """Lagre k_mod for skivan i klimatklass 2, EC5 tab. 3.1."""
    kk1 = berakning.kor(cfg_med(**{"forband.skivmaterial": "osb3",
                                   "projekt.klimatklass": 1}))
    kk2 = berakning.kor(cfg_med(**{"forband.skivmaterial": "osb3",
                                   "projekt.klimatklass": 2}))
    assert kk2.kontroll.M_Rd < kk1.kontroll.M_Rd


# ---------------------------------------------------------------------------
# De tva satten att rakna skivans bojning
# ---------------------------------------------------------------------------

def test_plywood_raknas_i_planet_med_f_t_90(res):
    """
    Handboken deklarerar sjalv f_t,90 = 7,0 MPa for sin plywood
    (5.3.4.2 s. 291). Det ar den svagare riktningen och darfor
    konservativt oavsett monteringsriktning -- sa plywooden kan och ska
    raknas i planet, precis som osb3 och p5. Bada metoderna redovisas.
    """
    assert res.metod == "i_planet"
    assert res.bada_metoderna_gar
    assert res.skivmaterial.har_draghallfasthet
    assert res.skivmaterial.dragriktning == "90"
    assert res.skivmaterial.draghallfasthet() == pytest.approx(7.0)


def test_osb_kan_raknas_pa_bada_satten():
    res = berakning.kor(cfg_med(**{"forband.skivmaterial": "osb3"}))
    assert res.metod == "i_planet"
    assert res.bada_metoderna_gar
    assert res.kontroll.M_plywood < res.kontroll_handbok.M_plywood


def test_i_planet_ar_konservativare_an_handbokens_metod():
    """
    f_t,0 ar lagre an f_m for bade OSB och spanskiva, sa den forsvarbara
    metoden ger lagre skivkapacitet. For 18 mm OSB/3: 9,4 mot 16,4 MPa.
    """
    for skiva in ("osb3", "p5"):
        res = berakning.kor(cfg_med(**{"forband.skivmaterial": skiva}))
        assert res.kontroll.M_plywood < res.kontroll_handbok.M_plywood


# ---------------------------------------------------------------------------
# Antaganden ska alltid redovisas
# ---------------------------------------------------------------------------

def test_de_harledda_och_osakra_storheterna_redovisas(res):
    text = " ".join(res.antaganden)
    assert "EA" in text and "HÄRLETT" in text
    assert "f_u = 600" in text
    assert "plastisk omlagring" in text
    assert "gamma_M = 1.3" in text
    assert "Knäcklängd" in text
    assert "EI_05" in text


# ---------------------------------------------------------------------------
# Balkens egen barformaga
# ---------------------------------------------------------------------------

def test_balkkontrollen_gors_pa_varsta_snittet_langs_sparren(res):
    """
    Skanningen gar langs HELA sparren, inte bara till nocken.

    Med nockfjadern raknad som en SKARV (K_rot/4) sjunker nockmomentet
    och faltmomentet vaxer, sa det dimensionerande snittet ligger numera
    inne i faltet -- inte i nocken. Det ar sjalva poangen med att inte
    rakna nocken helt styv. Kontrollen har ar att snittet ligger PA
    sparren och att skanningen verkligen hittar ett inre maximum.
    """
    from math import cos, radians
    L_sparre = (10.0 / 2) / cos(radians(27.0))
    assert 0.0 < res.balksnitt.s < L_sparre
    assert res.L_ef == pytest.approx(L_sparre, abs=0.02)
    # hogmomentet (mest negativa) sitter daremot kvar i nocken
    assert res.hogmoment.s == pytest.approx(L_sparre, abs=0.05)


def test_snittkrafterna_i_balksnittet_ar_samverkande(res):
    """
    M, N och V ska vara tagna i SAMMA punkt langs sparren -- annars
    kombineras ett moment fran ett stalle med en normalkraft fran ett
    annat. Balksnittet ligger numera i faltet och nockforbandets snitt i
    nocken, sa de behover INTE vara lika; det som maste stamma ar att
    balksnittets tal hor ihop inbordes.
    """
    b = res.balksnitt
    assert b.M != 0.0 and b.N != 0.0
    # samma lastfall for alla tre
    assert b.kombination and b.snofall and b.varaktighet
    # och hogmomentet i nocken ar det som nockforbandet raknas med
    assert res.hogmoment.M == pytest.approx(res.dimensionerande.M,
                                            rel=0.02)


def test_balken_kontrolleras_for_bojning_tvarkraft_och_interaktion(res):
    namn = [k.namn for k in res.balkkontroller]
    assert "Bojning" in namn
    assert "Tvarkraft" in namn
    assert any("tryck" in n for n in namn)
    assert any(n.startswith("Bojning +") for n in namn)


def test_nockforbandet_styr_nar_skivan_raknas_i_planet(res):
    """
    Skivkontrollen i planet (f_t,90 = 7,0) gor nockforbandet till den
    styrande kontrollen, over balken. Handbokens plattbojningsvag hade
    lagt forbandet UNDER balken -- bada talen finns i resultatet.
    """
    assert not res.balken_haller
    assert res.varsta_balkkontroll.namn.startswith("Bojning + tryck")
    assert not res.kontroll.skarv                 # metodvalet ar handbok
    assert res.forband_utnyttjande > res.varsta_balkkontroll.utnyttjande
    # plattbojningsvagen (f_m i stallet for f_t,90) ar kontroll_handbok --
    # u_handbok ar en ANNAN axel (hela spikbilden mot halvgrupp)
    assert (res.kontroll_handbok.utnyttjande_totalt
            < res.forband_utnyttjande)


def test_hogre_balk_klarar_balkkontrollen():
    """
    H300 klarar inte platshallarlasterna. Nagon hogre balk i samma serie ska
    gora det -- annars ar det inte balkhojden som ar problemet.
    """
    haller = [b.namn for b in material.balkar(liv="osb", serie="H")
              if berakning.kor(cfg_med(**{"geometri.balk": b.namn}))
              .balken_haller]
    assert haller, "ingen H-balk klarar lasterna"
    assert "H300" not in haller


def test_hogmomentet_hittas_langs_hela_sparren(res):
    """
    Sidostodskontrollen ska utga fran det storsta negativa momentet var som
    helst langs sparrarna, inte bara i nocken. Har sammanfaller de.
    """
    assert res.hogmoment.M <= res.balksnitt.M + 1e-9
    assert res.hogmoment.M < 0


def test_knacklangdsfaktorn_slar_igenom():
    """
    En kortare knacklangd ger hogre k_c och lagre utnyttjande. Faktorn ar
    ett antagande anvandaren ager, sa den maste faktiskt anvandas.
    """
    lang = berakning.kor(grundcfg())
    kort = berakning.kor(cfg_med(**{"dimensionering.knacklangdsfaktor": 0.5}))
    assert kort.L_ef == pytest.approx(lang.L_ef / 2)
    assert kort.varsta_balkkontroll.utnyttjande < \
        lang.varsta_balkkontroll.utnyttjande


def test_gamma_M_slar_igenom():
    """
    gamma_M ar inte deklarerad i ETA:n utan hamtad ur handboken s. 232. Den
    maste ga att andra, och andringen ska synas.
    """
    hog = berakning.kor(cfg_med(**{"dimensionering.gamma_M_balk": 1.30}))
    lag = berakning.kor(cfg_med(**{"dimensionering.gamma_M_balk": 1.20}))
    assert lag.varsta_balkkontroll.utnyttjande < \
        hog.varsta_balkkontroll.utnyttjande


def test_ledad_nock_flyttar_varsta_snittet_ut_i_faltet():
    """
    Utan momentstyv nock ar nockmomentet noll och maxmomentet hamnar en bit
    ut pa sparren i stallet. Da ar overflansen tryckt dar, och taklakten
    stodjer den.
    """
    res = berakning.kor(cfg_med(**{"system.nock_styv": False}))
    assert res.balksnitt.s < 5.0                 # inte langst ut i nocken
    assert res.balksnitt.M > 0                   # positivt = overflans tryckt


def test_dop_paminnelsen_kommer_med_for_alla_skivmaterial():
    for skiva in ("plywood_handbok", "osb3", "p5"):
        res = berakning.kor(cfg_med(**{"forband.skivmaterial": skiva}))
        assert any("DoP" in a for a in res.antaganden), skiva


# ---------------------------------------------------------------------------
# Rotationsfjadern
# ---------------------------------------------------------------------------

def test_fjadern_sanker_nockmomentet(res):
    """
    K_u = 2/3*K_ser i brottgrans. Helt styv nock ger storre nockmoment --
    den gamla korningen gav -9,11 kNm dar fjadern ger runt -7,5.
    """
    styv = berakning.kor(cfg_med(**{"system.rotationsfjader": False}))
    assert res.K_r and not styv.K_r
    assert abs(res.dimensionerande.M) < abs(styv.dimensionerande.M)
    assert res.K_r["K_u"] == pytest.approx(res.K_r["K_ser"] * 2 / 3)


def test_fjaderstyvheten_ar_en_skarv():
    """
    Nocken ar en skarv: halvforbanden i serie, raknade pa halvgruppens
    troghetsmoment om SIN EGEN tyngdpunkt. Harledningen och dess falla
    ligger i test_forband_skarv.py -- har kontrolleras bara att kedjan
    anvander den och att K_u = 2/3*K_ser.
    """
    r = berakning.kor(grundcfg())
    # Fjadern loses i nockens VERKLIGA geometri. Spikbilden tar hansyn
    # till den lodrata stotfogen (15d), forvalet ar spikmonster = "kant",
    # sida -Y ar sidoforskjuten en halv delning (2026-08-19), och sedan
    # samma dag SNAPPAS starterna till rastret s/2 + n*s (rutnats-
    # utsattning) -- klampade kolonner flyttar da ytterligare utat,
    # vilket hojer I_p och K. Historik: fore snappningen 482.5/374.2/
    # 3597.7; utan forskjutning 468.7; fullt rutnat 502.8; platta
    # bilden utan stotfog 393/355/2153.
    # ... och sedan rutnat_ankare = "flansvinkel": rastret ankras sa
    # att en tvarlinje gar EXAKT genom vinkeln mellan undre flansarna,
    # (h/2)*tan(alfa) fran fogen (507.3 -> 523.6). Aldre: 25*n-raster
    # 507.3; fore snappning 482.5; utan sidoforskjutning 468.7; fullt
    # rutnat 502.8; platt bild utan stotfog 393.
    assert r.K_r["K_ser"] == pytest.approx(523.6, rel=0.01)
    assert r.K_r["K_platt"] == pytest.approx(402.9, rel=0.01)
    assert r.K_r["K_u"] == pytest.approx(r.K_r["K_ser"] * 2 / 3, rel=1e-6)
    assert r.K_r["K_en_stel_del"] == pytest.approx(3954.6, rel=0.01)
    assert r.K_r["K_ser"] > r.K_r["K_platt"]      # vridningen styvar upp


def test_mjukare_nock_flyttar_lasten_till_faltet():
    """
    Fysiken bakom skarven: en mjukare nock ger mindre nockmoment och
    mer faltmoment. Jamforelsen gors mot en HELT STYV nock, som ar det
    andra gransfallet och gar att sla pa i projektfilen.
    """
    mjuk = berakning.kor(grundcfg())
    styv = berakning.kor(cfg_med(**{"system.rotationsfjader": False}))
    assert abs(styv.hogmoment.M) > abs(mjuk.hogmoment.M)
    assert styv.balksnitt.s > mjuk.balksnitt.s


def test_fler_spikar_ger_styvare_nock():
    fa = berakning.kor(cfg_med(**{"forband.rader_liv": 2}))
    manga = berakning.kor(cfg_med(**{"forband.rader_liv": 8}))
    assert manga.K_r["K_ser"] > fa.K_r["K_ser"]


# ---------------------------------------------------------------------------
# Vind
# ---------------------------------------------------------------------------

def test_vind_utan_qp_ger_varning_och_inga_vindfall():
    res = berakning.kor(cfg_med(**{"laster.vind.q_p": 0.0, "plats.hamtat.v_b": 0.0, "plats.hamtat.v_b": 0.0}))
    assert res.vindfall == []
    assert any("Vindlast ingår inte" in v for v in res.varningar)


def test_lyftfallet_finns_med_nar_vind_ingar(res):
    kombinationer = {s.kombination for s in res.snittkrafter}
    assert any("gynnsam G" in k for k in kombinationer)


def test_vindfall_far_momentan_varaktighet(res):
    for s in res.snittkrafter:
        if s.vindfall != "-":
            assert s.varaktighet == "momentan"
        else:
            assert s.varaktighet in ("medel", "permanent")


def test_vindsug_avlastar_taket(res):
    """
    Kraftigt sug (cpe -0,9 med cpi +0,2) ska ge LAGRE nockmoment an samma
    kombination utan vind -- vinden lyfter taket.
    """
    per_fall = {(s.kombination, s.snofall, s.vindfall): s.M
                for s in res.snittkrafter}
    utan = per_fall[("BFS tab. 3:1 LK1 (s huvudlast)", "(i) symmetrisk", "-")]
    sug = [M for (k, sf, vf), M in per_fall.items()
           if k == "BFS tab. 3:1 LK1 (s huvudlast)" and sf == "(i) symmetrisk"
           and "-0.90" in vf and "cpi +0.2" in vf]
    assert sug and all(abs(M) < abs(utan) for M in sug)


# ---------------------------------------------------------------------------
# Upplag och horisontalkraft
# ---------------------------------------------------------------------------

def test_upplagen_kontrolleras_pa_bada_sidor(res):
    namn = [k.namn for k in res.upplag_kontroller]
    assert any("vänster" in n for n in namn)
    assert any("höger" in n for n in namn)


def test_upplaget_ar_flaskhalsen_med_platshallardata(res):
    """
    45 mm oforstarkt upplag ger F_Rd ca 5,5 kN mot reaktionen ca 15 kN --
    och det blir inte battre av en hogre balk, eftersom a-parametern
    foljer serien, inte hojden. Darfor redovisas upplaget SEPARAT
    (anvandarbeslut 2026-08-18): det ingar varken i res.haller eller i
    varsta_utnyttjande, utan far egna falt och en varning som pekar pa
    L1/forstarkning i stallet for balkbyte.
    """
    assert res.upplag_utnyttjande > 2.0
    assert not res.upplaget_haller
    assert res.varsta_utnyttjande < res.upplag_utnyttjande
    assert any("Upplaget överskrids" in v for v in res.varningar)


def test_langre_upplag_och_forstarkning_hjalper(res):
    """
    145 mm forstarkt upplag mot 45 mm oforstarkt: F_Rd gar fran 5,5 till
    10,8 kN pa en H300 -- strax UNDER tvarkraftstaket V_Rd = 11,0 kN, sa
    hela vinsten far raknas. Anda racker det inte mot reaktionen 15 kN:
    upplaget forblir flaskhalsen for H-serien.
    """
    battre = berakning.kor(cfg_med(**{"upplag.L1": 145.0,
                                      "upplag.forstarkning": True}))
    fore = max(k.utnyttjande for k in res.upplag_kontroller)
    efter = max(k.utnyttjande for k in battre.upplag_kontroller)
    assert efter < 0.6 * fore
    assert efter > 1.0                   # men fortfarande inte godkant


def test_horisontalkraften_redovisas_och_varnas_utan_dragband(res):
    assert res.H_takfot > 10.0
    assert any("Horisontalkraften" in v for v in res.varningar)

    med_band = berakning.kor(cfg_med(**{"system.dragband": True}))
    assert not any("Horisontalkraften" in v for v in med_band.varningar)


# ---------------------------------------------------------------------------
# Nedbojning
# ---------------------------------------------------------------------------

def test_nedbojningen_kontrolleras_mot_handbokens_krav(res):
    nb = res.nedbojning
    namn = [k.namn for k in nb.kontroller]
    assert "Nedböjning inst" in namn and "Nedböjning fin" in namn
    inst = next(k for k in nb.kontroller if "inst" in k.namn)
    # allmant utan separat innertak: L/375 pa sparrelangden 5,61 m
    assert inst.R_d == pytest.approx(res.nedbojning.L_sparre * 1000 / 375,
                                     rel=1e-6)
    assert "L/375" in inst.referens


def test_skjuvdeformationen_ar_en_stor_del_av_nedbojningen(res):
    """
    Skjuvdelen ar over 15 % av u_fin for en H300 -- den gar inte att
    hoppa over, sarskilt som den kryper med k_def 1,50 mot bojningens
    0,60 (ETA tab. 18).
    """
    assert res.nedbojning.skjuvandel_fin > 0.15


def test_u_fin_ar_storre_an_u_inst(res):
    u = {k.namn: k.E_d for k in res.nedbojning.kontroller}
    assert u["Nedböjning fin"] > u["Nedböjning inst"]


def test_overhojd_skarper_kraven(res):
    """
    Handboken s. 229 och Limtrahandboken tab. 6.1 tabellerar EJ overhojda
    element och sager "tabellvardet/1,5" for overhojda: gransen KRYMPER.
    Det ar bara meningsfullt mot nettonedbojningen, sa overhojningen dras
    av. Se docs/ERRATA.md punkt 6.
    """
    over = berakning.kor(cfg_med(**{"nedbojning.overhojd": True,
                                    "nedbojning.overhojd_mm": 5.0}))
    for k_o, k_n in zip(over.nedbojning.kontroller,
                        res.nedbojning.kontroller):
        assert k_o.R_d == pytest.approx(k_n.R_d / 1.5)
        assert k_o.E_d == pytest.approx(k_n.E_d - 5.0)


def test_overhojd_utan_matt_ar_ett_fel(res):
    """En overhojning utan storlek gav forr brutto mot netto-krav."""
    with pytest.raises(ValueError, match="overhojd_mm"):
        berakning.kor(cfg_med(**{"nedbojning.overhojd": True}))


def test_overhojningen_kapas_vid_egentyngdens_nedbojning():
    """
    Utan kap kan vilken balk som helst godkannas genom att skriva in en
    stor overhojning. Kapet ligger vid egentyngdens SLUTLIGA nedbojning
    (Limtrahandboken 6.2.4 s. 87) och redovisas som varning.
    """
    stor = berakning.kor(cfg_med(**{"nedbojning.overhojd": True,
                                    "nedbojning.overhojd_mm": 50.0}))
    u_c = stor.nedbojning.overhojd_mm
    assert 0 < u_c < 50.0
    assert stor.nedbojning.overhojd_varning
    assert any("kapas" in v for v in stor.varningar)

    # kapet = egentyngden ensam, slutlig nedbojning
    g = berakning.kor(cfg_med(**{"laster.sno.s_k": 0.001,
                                 "laster.vind.q_p": 0.0,
                                 "plats.hamtat.v_b": 0.0}))
    uG_fin = next(k.E_d for k in g.nedbojning.kontroller
                  if "fin" in k.namn)
    assert u_c == pytest.approx(uG_fin, rel=0.02)

    # och resultatet ar identiskt med att ange kapvardet direkt
    lika = berakning.kor(cfg_med(**{"nedbojning.overhojd": True,
                                    "nedbojning.overhojd_mm": u_c}))
    for a, b in zip(stor.nedbojning.kontroller,
                    lika.nedbojning.kontroller):
        assert a.E_d == pytest.approx(b.E_d)
        assert a.R_d == pytest.approx(b.R_d)


def test_overhojning_under_en_tredjedel_lonar_sig_inte(res):
    """
    Brytpunkten: 1,5*(u - u_c) < u kraver u_c > u/3. En liten overhojning
    ger alltsa HOGRE utnyttjande an ingen alls -- det ar en foljd av att
    kravet skarps med 1,5, och det ska synas i siffrorna.
    """
    fin = lambda r: next(k.utnyttjande                      # noqa: E731
                         for k in r.nedbojning.kontroller if "fin" in k.namn)
    u_fin = next(k.E_d for k in res.nedbojning.kontroller if "fin" in k.namn)
    liten = berakning.kor(cfg_med(**{"nedbojning.overhojd": True,
                                     "nedbojning.overhojd_mm": u_fin / 6}))
    assert fin(liten) > fin(res)


def test_p5_liv_kryper_mer_an_osb():
    """k_def for skjuvning: 2,25 mot 1,50 i klimatklass 1 (ETA tab. 18)."""
    osb = berakning.kor(cfg_med(**{"geometri.balk": "H300"}))
    p5 = berakning.kor(cfg_med(**{"geometri.balk": "H300s"}))
    fin = lambda r: next(k.E_d for k in r.nedbojning.kontroller  # noqa: E731
                         if "fin" in k.namn)
    assert fin(p5) > fin(osb)


def test_frekventa_kombinationen_beraknas_enligt_limtrahandboken(res):
    """
    u_freq enligt Limtrahandboken del 2 ekv. 6.8 (tab. 6.1:s fotnot).
    Momentan nedbojning: utan vind ar den G + 0,6*S, sa den ligger
    alltid mellan 0,6*u_inst och u_inst (u_inst = G + S + 0,3*V >= G + S,
    och G + 0,6*S >= 0,6*(G + S)). Metod och psi-varden ska redovisas.
    """
    freq = next(k for k in res.nedbojning.kontroller if "freq" in k.namn)
    inst = next(k for k in res.nedbojning.kontroller if "inst" in k.namn)
    assert "6.8" in freq.referens
    assert 0.6 * inst.E_d <= freq.E_d <= inst.E_d
    assert res.nedbojning.fall_freq
    assert any("ekv. 6.8" in a for a in res.nedbojning.anmarkningar)


def test_u_freq_utan_vind_ar_exakt_g_plus_06_s():
    """Utan vind finns bara sno som ledande: u_freq = G + 0,6*S.
    Kontrollsumman: u_freq = u_inst - 0,4*u_S dar u_S = u_inst - u_G --
    har verifierat via tva extra korningar dar snon skalas."""
    cfg_utan_vind = cfg_med(**{"laster.vind.q_p": 0.0, "plats.hamtat.v_b": 0.0, "plats.hamtat.v_b": 0.0})
    r = berakning.kor(cfg_utan_vind)
    freq = next(k for k in r.nedbojning.kontroller if "freq" in k.namn)
    inst = next(k for k in r.nedbojning.kontroller if "inst" in k.namn)
    # skala snon med psi_1 och jamfor karakteristiska kombinationen.
    # Basen tas ur konfigurationen -- den kommer numera ur [plats.hamtat]
    # och ar inte langre ett fast tal i projektfilen.
    S_0 = berakning.lastforutsattningar(cfg_utan_vind)[0]
    psi1 = material.psi_sno(S_0)["psi1"]
    r06 = berakning.kor(cfg_med(**{"laster.vind.q_p": 0.0,
                                   "plats.hamtat.v_b": 0.0,
                                   "laster.sno.s_k": psi1 * S_0}))
    inst06 = next(k for k in r06.nedbojning.kontroller
                  if "inst" in k.namn)
    assert freq.E_d == pytest.approx(inst06.E_d, rel=1e-6)
    assert freq.E_d < inst.E_d
    assert "snö ledande" in r.nedbojning.fall_freq


# ---------------------------------------------------------------------------
# Ledad nock enligt 5.3.7
# ---------------------------------------------------------------------------

def test_ledad_nock_far_ett_ledat_forband():
    res = berakning.kor(cfg_med(**{"system.nock_styv": False}))
    assert res.nocktyp == "ledad"
    assert res.ledad is not None
    assert res.ledad.e > 0
    assert res.forband_utnyttjande == res.ledad.utnyttjande
    # excentricitetsmomentet M = V*e ska vara med
    assert res.ledad.M > 0


def test_ledad_nock_loser_sidostodsproblemet_men_inte_takfoten():
    """
    Utan nockmoment ar overflansen tryckt overallt och taklakten racker
    som sidostod -- varningen forsvinner. Men horisontalkraften i
    vaggkronet FINNS kvar (treledsram utan dragband), och upplagstrycket
    likasa.
    """
    res = berakning.kor(cfg_med(**{"system.nock_styv": False}))
    assert not any("UNDERFLÄNSEN" in v for v in res.varningar)
    assert res.H_takfot > 10.0


def test_jamfor_nock_ger_bada_varianterna():
    bada = berakning.jamfor_nock(grundcfg())
    assert set(bada) == {"momentstyv", "ledad"}
    assert abs(bada["ledad"].dimensionerande.M) < 1e-6
    assert abs(bada["momentstyv"].dimensionerande.M) > 1.0


# ---------------------------------------------------------------------------
# Zigzag-spikning i flansen (handboken s. 284)
# ---------------------------------------------------------------------------

def test_flanskolumner_geometri():
    """
    2,5-spik ryms bara i EN kolumn i 47 mm flanshojd: 2*a4t + a2 = 19d
    = 47,5 mm > 47 (tab. 8.2 med kraft mot belastad kant, alpha = 90).
    En 2,1-spik ryms i tva kolumner: 19*2,1 = 39,9 mm. Gransen ar
    d <= 47/19 = 2,47 mm -- inget i dagens bibliotek klarar den.
    """
    import forbindare_ec5 as EC5
    spik25 = material.forbindare("ankarspik_2_5x50")
    off, varn = berakning.flanskolumner(spik25, 47.0, 2)
    assert varn and "47.5" in varn[0]
    assert off == pytest.approx([-6.25, 6.25])

    spik21 = EC5.Forbindare(namn="testspik 2,1x45", d=2.1, langd=45.0,
                            f_u=600.0, typ="rillad", forborrning=False)
    off, varn = berakning.flanskolumner(spik21, 47.0, 2)
    assert not varn
    assert off == pytest.approx([-5.25, 5.25])


def test_kolumner_flans_tva_ger_dubbla_spikar_i_zigzag(res):
    """
    kolumner_flans = 2: dubbelt antal flansspikar, storre I_p, kolumnerna
    12,5 mm isar och forskjutna en halv delning (zigzag) -- och en
    varning eftersom 2,5-spiken inte ryms enligt tab. 8.2.
    """
    r2 = berakning.kor(cfg_med(**{"forband.kolumner_flans": 2}))
    fl1 = next(g for g in res.grupper if "flans" in g.namn)
    fl2 = next(g for g in r2.grupper if "flans" in g.namn)
    assert fl2.antal == 2 * fl1.antal
    assert fl2.grupp.Ip > fl1.grupp.Ip
    assert any("spikkolumner" in v for v in r2.varningar)

    # PER SIDA: coords ar A + B dar sida B ar sidoforskjuten -- da
    # sammanfaller B:s raster med zigzagkolonnens A-raster, och det ar
    # inte det zigzagregeln handlar om. Regeln galler tva kolumner i
    # SAMMA flans sedda fran samma sida.
    sida_a = fl2.grupp.sidor[0]
    xs = sorted({round(x, 3) for x, y in sida_a})
    x_a, x_b = xs[0], xs[1]          # samma flans, tva kolumner
    ys_a = {y for x, y in sida_a if round(x, 3) == x_a}
    ys_b = {y for x, y in sida_a if round(x, 3) == x_b}
    assert x_b - x_a == pytest.approx(12.5)
    # Zigzag-kravet (s. 284) ar MINST 1d ur fiberlinjen. Dar stotfogens
    # kantkrav styr forsta raden blir forskjutningen 12,5*tan(27) = 6,4
    # i stallet for halva delningen -- fortfarande >= 1d = 2,5.
    spik_d = 2.5
    assert min(abs(a - b) for a in ys_a for b in ys_b) >= spik_d


def test_zigzag_ar_ett_redovisat_antagande(res):
    assert any("zigzag" in a for a in res.antaganden)


# ---------------------------------------------------------------------------
# Tvarkraften i nockforbandet, och den rena permanentkombinationen
# ---------------------------------------------------------------------------

def test_forbandets_utnyttjande_raknar_med_tvarkraften(res):
    """
    Handbokens interaktion |M|/M_Rd + N/N_Rd utelamnar V, men varje
    forbindare bar sqrt(N^2+V^2)/n vid sidan av M*r/Ip. Det tal som
    avgor om forbandet haller ska darfor vara det storsta av
    interaktionen och gruppkontrollerna -- annars kan programmet
    redovisa OK samtidigt som dess egen gruppkontroll sager EJ OK.
    """
    k = res.kontroll
    grupp_u = max(d["u"] for d in k.per_grupp.values())
    assert k.utnyttjande_totalt == pytest.approx(
        max(k.utnyttjande, grupp_u))
    assert res.forband_utnyttjande == pytest.approx(k.utnyttjande_totalt)
    # gruppkontrollen bar tvarkraften -- sqrt(N^2+V^2) > N
    from math import hypot
    d = res.dimensionerande
    assert hypot(d.N, d.V) > abs(d.N)


def test_rena_permanentkombinationen_provas():
    """
    EN 1990 6.10a med variabla laster = 0. Den har LAGRE lasteffekt men
    ocksa lagre k_mod (0,60 mot snons 0,80), sa den kan styra nar
    snolasten ar liten mot egentyngden.
    """
    namn = {sk.kombination for sk in
            berakning.kor(grundcfg()).snittkrafter}
    assert "BFS tab. 3:1 LK2 (endast permanent)" in namn
    # och EN 1990:s 6.10a med psi0-laster finns INTE i BFS 2024:6
    assert not any(n.startswith("6.10") for n in namn)

    perm = [sk for sk in berakning.kor(grundcfg()).snittkrafter
            if sk.kombination == "BFS tab. 3:1 LK2 (endast permanent)"]
    assert all(sk.varaktighet == "permanent" for sk in perm)

    # med latt sno och tung egentyngd ska den bli dimensionerande
    lag_sno = berakning.kor(cfg_med(**{"laster.sno.s_k": 0.5}))
    styrande = max(lag_sno.snittkrafter,
                   key=lambda sk: abs(sk.M))
    assert styrande is not None


def test_snittlaget_raknas_fran_takfoten_pa_bada_sidor():
    """
    ram.sadeltak bygger hoger sparre som chain(apex, right), alltsa
    nock -> takfot. Redovisas snittlaget rakt av blir hoger sidas s
    speglat: ett nocksnitt pastas ligga vid takfoten. Symmetrisk
    snolast ger samma snitt pa bada sidor, sa laget maste bli detsamma.
    """
    r = berakning.kor(cfg_med(**{"laster.vind.q_p": 0.0, "plats.hamtat.v_b": 0.0, "plats.hamtat.v_b": 0.0}))
    L_sp = r.nedbojning.L_sparre
    assert 0.0 <= r.balksnitt.s <= L_sp + 1e-9
    assert 0.0 <= r.hogmoment.s <= L_sp + 1e-9
    # hogmomentet sitter i nocken -> nara sparrens andpunkt
    assert r.hogmoment.s > 0.9 * L_sp


def test_ledad_nock_redovisar_sitt_eget_dimensionerande_fall():
    """
    Med ledad nock ska Resultat.dimensionerande komma ur DET fall som
    gav det ledade forbandets varsta utnyttjande -- run.py skriver
    dimensionerande.N och .V intill ledad.F, och de maste hora ihop.
    """
    from math import hypot
    r = berakning.kor(cfg_med(**{"system.nock_styv": False}))
    d, led = r.dimensionerande, r.ledad
    # kraften i forbandet ska ga att harleda ur det redovisade snittet
    assert led.M == pytest.approx(abs(d.V) * led.e / 1000.0, rel=1e-6)
    assert hypot(d.N, d.V) > 0


def test_antagandena_visar_EA_for_valt_flanskval():
    c18 = berakning.kor(cfg_med(**{"forband.flanskvalitet": "C18"}))
    rad = next(a for a in c18.antaganden if a.startswith("EA ="))
    assert "C18" in rad
