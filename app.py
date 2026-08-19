#!/usr/bin/env python3
"""
Webbgranssnitt for dimensionering av sadeltakstol i lattbalk.

    python -m streamlit run app.py

Filen innehaller INGEN ingenjorslogik. Den bygger en cfg-dict ur formularet
och lamnar den till berakning.kor(), precis som run.py gor. Ska nagot raknas
annorlunda ska det andras i src/, inte har.

Alla materialalternativ kommer ur input/material/. Vill du att ett material
inte ska ga att valja, ta bort det ur biblioteket -- det finns inga
hardkodade alternativ i den har filen.
"""

import copy
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st                               # noqa: E402

import berakning                                     # noqa: E402
import dimensionera                                  # noqa: E402
import material
import ritning3d                                    # noqa: E402

PROJEKTFIL = Path(__file__).parent / "input" / "projekt.toml"

# (Serie-/livnamnen behovs inte langre i granssnittet -- balken valjs
# direkt pa namn -- men behall dem sa lange run.py/dokumentation pekar hit.)
SERIENAMN = {"H": "H - fläns 47x47", "HM": "HM - fläns 47x60",
             "HI": "HI - fläns 47x70", "HB": "HB - fläns 47x97"}
LIVNAMN = {"osb": "OSB/3", "spanskiva": "Spånskiva P5"}
VARAKTIGHETSNAMN = {"permanent": "Permanent", "lang": "Lång",
                    "medel": "Medellång", "kort": "Kort",
                    "momentan": "Momentan"}


# Autosparet. Miljovariabeln finns for TESTERNA: sviten raderar
# autosparet for att fa deterministiska korningar, och utan omdirigering
# raderade varje testkorning UTVECKLARENS pagaende session (upptackt
# 2026-08-19 -- "data jag skriver in stannar inte").
SENASTE = Path(os.environ.get(
    "TAKSTOL_AUTOSPAR",
    str(Path(__file__).parent / "input" / ".senaste_session.json")))

# Hostat lage (Streamlit Community Cloud m.fl.): fil-autosparet stangs
# av -- pa en delad server skulle ALLA besokare dela samma sparfil och
# se varandras inmatning. Sessionen lever da bara i webblasarfliken.
HOSTAT = (os.environ.get("HOSTNAME") == "streamlit"
          or os.path.exists("/home/appuser")
          or os.environ.get("TAKSTOL_HOSTAT") == "1")


@st.cache_data
def las_grundcfg():
    with open(PROJEKTFIL, "rb") as fh:
        return tomllib.load(fh)


def _djupmerge(bas, over):
    """over laggs pa bas rekursivt; dict-varden mergas, annat ersatts."""
    ut = dict(bas)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(ut.get(k), dict):
            ut[k] = _djupmerge(ut[k], v)
        else:
            ut[k] = v
    return ut


def las_startcfg():
    """
    Projektfilen ar grunden; finns ett autospar fran en tidigare session
    mergas det OVANPA, sa att en omladdning av sidan inte nollstaller
    inmatningen. Autosparet ar JSON (inte TOML) med flit: projekt.toml
    ar det handredigerade originalet med sina kommentarer, och det rors
    aldrig av appen.

    Returnerar (cfg, sparad_tidpunkt|None, steg).
    """
    import copy
    import json

    if HOSTAT:
        return copy.deepcopy(las_grundcfg()), None, 1

    cfg = copy.deepcopy(las_grundcfg())
    if not SENASTE.exists():
        return cfg, None, 1
    try:
        with open(SENASTE, encoding="utf-8") as fh:
            sparat = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return cfg, None, 1
    tid = sparat.pop("_sparad", None)
    steg = int(sparat.pop("_steg", 1))
    return _djupmerge(cfg, sparat), tid, steg


def spara_senaste(cfg, steg):
    """Skriver autosparet -- bara nar nagot faktiskt andrats."""
    if HOSTAT:
        return
    import datetime
    import json

    # "Las om projektfilen" raderar filen och kor om appen -- da far
    # slutet av JUST DEN korningen inte aterskapa den. Nasta riktiga
    # inmatning sparar som vanligt.
    if st.session_state.pop("_hoppa_over_autospar", False):
        return
    data = dict(cfg, _steg=steg)
    nyckel = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if st.session_state.get("_senast_sparat") == nyckel:
        return
    st.session_state["_senast_sparat"] = nyckel
    data["_sparad"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(SENASTE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass                      # autosparet ar bekvamlighet, inte data


# ---------------------------------------------------------------------------
# Formularet
# ---------------------------------------------------------------------------

def steg1_forutsattningar(cfg):
    """
    Steg 1: var huset star och vad som lastar det, samt vilken takstol
    som ska studeras. Ingenting harifran beror pa matten.
    """
    c = copy.deepcopy(cfg)
    p, sysm = c["projekt"], c["system"]

    st.subheader("1. Plats, laster och klasser")

    v, h = st.columns([3, 2])
    with v:
        st.markdown("**Plats och klimatlaster**")
        _platssektion(c)
    with h:
        st.markdown("**Klasser**")
        p["sakerhetsklass"] = st.radio(
            "Säkerhetsklass", [1, 2, 3], index=int(p["sakerhetsklass"]) - 1,
            horizontal=True,
            help="BFS 2024:6 2 kap. 2 §: gamma_d 0,83 / 0,91 / 1,00.")
        p["klimatklass"] = st.radio(
            "Klimatklass", [1, 2], index=int(p["klimatklass"]) - 1,
            horizontal=True,
            help="Styr k_mod och k_def. 1 = uppvärmt inomhus, "
                 "2 = ventilerat kallutrymme.")
        nb = c.setdefault("nedbojning", {})
        nb["byggnadstyp"] = st.selectbox(
            "Nedböjningskrav", list(material.NEDBOJNING_DATA["tak"]),
            format_func=lambda n: material.NEDBOJNING_DATA["tak"][n]["namn"],
            index=_index(list(material.NEDBOJNING_DATA["tak"]),
                         nb.get("byggnadstyp", "allmant_utan_tak")))

    st.divider()
    # Appen ar slimad till EN takstolstyp: sadeltakstol med MOMENTSTYV
    # nock (anvandarbeslut 2026-08-19). Ledad nock och b1 finns kvar i
    # berakningskarnan (forband.ledad_nock, ram.takstol_b1, run.py
    # --jamfor) med sina tester, men ar inte valbara har.
    sysm["nock_styv"] = True

    k1, k2, k3 = st.columns(3)
    sysm["rotationsfjader"] = k1.checkbox(
        "Rotationsfjäder i nocken",
        bool(sysm.get("rotationsfjader", True)),
        help="K_r ur spikgruppernas K_ser (EC5 tab. 7.1). Nocken är en "
             "skarv, så halvförbanden sitter i serie. Helt styv nock "
             "överskattar nockmomentet men underskattar fältmoment och "
             "nedböjning.")
    sysm["dragband"] = k2.checkbox("Dragband i takfotsnivå",
                                   bool(sysm["dragband"]))
    sysm["upplag"] = k3.radio("Upplag", ["ledat", "fast"],
                              index=0 if sysm["upplag"] == "ledat" else 1,
                              horizontal=True)
    return c


def steg2_matt(cfg):
    """Steg 2: matten. Illustrationen och resultaten kommer under."""
    c = copy.deepcopy(cfg)
    g, fb = c["geometri"], c["forband"]
    upl = c.setdefault("upplag", {})
    nb = c.setdefault("nedbojning", {})

    st.subheader("2. Mått och utformning")
    flik_g, flik_b, flik_u, flik_f = st.tabs(
        ["Geometri", "Balk", "Upplag", "Nockförband"])

    with flik_g:
        k1, k2, k3 = st.columns(3)
        g["spannvidd"] = k1.number_input("Spännvidd [m]", 2.0, 30.0,
                                         float(g["spannvidd"]), 0.5)
        g["taklutning"] = k2.number_input("Taklutning [grader]", 5.0, 60.0,
                                          float(g["taklutning"]), 1.0)
        g["cc"] = k3.number_input("c/c takstolar [m]", 0.3, 1.5,
                                  float(g["cc"]), 0.05)
        k4, k5 = st.columns(2)
        g["cc_lakt"] = k4.number_input(
            "c/c takläkt [m]", 0.1, 1.5, float(g.get("cc_lakt", 0.3)), 0.05,
            help="Sidostöd av ÖVERflänsen, provas mot ETA tab. 19.")
        g["sidostod_underflans"] = k5.number_input(
            "Sidostöd underfläns [mm]", 0.0, 2000.0,
            float(g.get("sidostod_underflans", 0.0)), 50.0,
            help="0 = inget. Vid negativt moment är underflänsen tryckt "
                 "och behöver eget sidostöd för att M_k ska gälla.")

    with flik_b:
        # EN valjare pa balknamnet (anvandarbeslut 2026-08-19). De
        # gamla Serie/Livmaterial-valen skrevs aldrig till cfg, sa
        # balkvalet overlevde inte en omladdning: serien aterstalldes
        # till H och den sparade balken hittades inte i listan. Nu ar
        # g["balk"] enda tillstandet, och det autosparas som allt annat.
        alla_balkar = material.balkar()
        k1, k2 = st.columns([3, 2])
        balk = k1.selectbox(
            "Balk", alla_balkar,
            format_func=lambda b: f"{b.namn}  -  M_k {b.M_k} kNm, "
                                  f"V_k {b.V_k} kN",
            index=_balkindex(alla_balkar, g["balk"]),
            help="Hela ETA-biblioteket: serie H/HM/HB/HI x höjd; "
                 "s-suffix = spånskiveliv P5 (högre tvärkrafts-"
                 "kapacitet, kryper mer), annars OSB/3-liv.")
        g["balk"] = balk.namn
        fb["flanskvalitet"] = k2.selectbox(
            "Flänskvalitet", list(material.flanskvaliteter()),
            index=_index(list(material.flanskvaliteter()),
                         fb.get("flanskvalitet", "C30plus")))
        st.caption(f"ETA tab. 19: sidostöd av tryckflänsen högst "
                   f"**{balk.sidostod_max:.0f} mm** för serie "
                   f"{balk.serie}. Fri livhöjd {balk.h_liv:.0f} mm, "
                   f"flänsbredd {balk.b_flans:.0f} mm.")
        if not balk.har_dragkapacitet:
            st.warning("Balken saknar användbar dragkapacitet i ETA:n, "
                       "se ERRATA punkt 4.", icon=":material/warning:")

    with flik_u:
        k1, k2 = st.columns(2)
        upl["L1"] = k1.number_input("Upplagslängd L1 [mm]", 45.0, 300.0,
                                    float(upl.get("L1", 45.0)), 5.0,
                                    help="ETA ekv. 3-5. Minst 45 mm; "
                                         "effektivt högst 150 vid "
                                         "ändupplag.")
        upl["overhang_y"] = k2.number_input(
            "Utstick y [mm]", 0.0, 1000.0,
            float(upl.get("overhang_y", 0.0)), 10.0)
        upl["forstarkning"] = st.checkbox(
            "Livförstärkning vid upplaget",
            bool(upl.get("forstarkning", False)),
            help="ETA fig. 3: skivor på båda sidor, minst h/2 breda.")
        nb["overhojd"] = st.checkbox(
            "Överhöjd konstruktion", bool(nb.get("overhojd", False)),
            help="Handboken s. 229 tabellerar EJ överhöjda element och "
                 "säger 'tabellvärdet/1,5' för överhöjda: kravet SKÄRPS "
                 "och gäller då nettonedböjningen. Se ERRATA punkt 6.")
        if nb["overhojd"]:
            nb["overhojd_mm"] = st.number_input(
                "Överhöjning [mm]", 1.0, 200.0,
                float(nb.get("overhojd_mm", 0.0) or 10.0), 1.0,
                help="Kapas vid egentyngdens slutliga nedböjning. Lönar "
                     "sig först när den överstiger en tredjedel av "
                     "nedböjningen, eftersom kravet samtidigt skärps.")

    with flik_f:
        k1, k2 = st.columns(2)
        skivor = material.skivnamn()
        fb["skivmaterial"] = k1.selectbox(
            "Skivmaterial", skivor, format_func=material.visningsnamn_skiva,
            index=_index(skivor, fb["skivmaterial"]))
        fb["skiva_t"] = k2.number_input("Skivtjocklek [mm]", 6.0, 40.0,
                                        float(fb["skiva_t"]), 1.0,
                                        help=f"Livet är indraget "
                                             f"{(balk.b_flans - balk.t_liv) / 2:.1f} mm "
                                             f"på {balk.namn} -- "
                                             f"livförstärkningen bör fylla "
                                             f"det.")
        k3, k4 = st.columns(2)
        fb["skiva_hojd_liv"] = k3.number_input(
            "Livförstärkningens höjd [mm]", 50.0, 500.0,
            float(fb["skiva_hojd_liv"]), 1.0,
            help=f"Fri livhöjd för {balk.namn}: {balk.h_liv:.0f} mm.")
        fb["skiva_hojd_ytter"] = k4.number_input(
            "Utanpåliggande skivas höjd [mm]", 50.0, 600.0,
            float(fb["skiva_hojd_ytter"]), 1.0)
        forb = material.forbindarnamn()
        k5, k6, k7 = st.columns(3)
        fb["forbindare_flans"] = k5.selectbox(
            "Förbindare mot fläns", forb,
            format_func=material.visningsnamn_forbindare,
            index=_index(forb, fb["forbindare_flans"]))
        fb["forbindare_liv"] = k6.selectbox(
            "Förbindare mot liv", forb,
            format_func=material.visningsnamn_forbindare,
            index=_index(forb, fb["forbindare_liv"]))
        fb["cc_forbindare"] = k7.number_input(
            "c/c förbindare [mm]", 5.0, 200.0,
            float(fb["cc_forbindare"]), 1.0)
        fb["spikmonster"] = st.radio(
            "Spikmönster i livet", ["rutnat", "kant"],
            index=0 if fb.get("spikmonster", "rutnat") == "rutnat" else 1,
            horizontal=True,
            help="'kant' är handbokens ramspikning (fig. 5.30): rader "
                 "längs skivans kanter + fulla kolumner vid ändarna, "
                 "tomt i mitten. 'rutnat' är ett fullt rutnät.")
        m0, m1, m2, m3 = st.columns(4)
        fb["kolumner_flans"] = m0.number_input(
            "Kol. fläns", 1, 4, int(fb.get("kolumner_flans", 1)),
            help="Spikkolumner per fläns. Zigzag enligt handboken s. 284.")
        fb["rader_flans"] = m1.number_input("Rader fläns", 1, 40,
                                            int(fb["rader_flans"]))
        fb["kolumner_liv"] = m2.number_input("Kol. liv", 1, 40,
                                             int(fb["kolumner_liv"]))
        fb["rader_liv"] = m3.number_input("Rader liv", 1, 40,
                                          int(fb["rader_liv"]))
        fb["kontakt_i_foget"] = st.checkbox(
            "Kontakttryck i fogen", bool(fb.get("kontakt_i_foget", False)),
            help="Handboken s. 290 / EN 1995-1-1 8.8.5: halva "
                 "normalkraften via kontakt om spalten är högst "
                 "1,5/3,0 mm. Gäller bara tryck.")
    return c


def _platssektion(c):
    """
    Platsens lastforutsattningar. S_0 och v_b hamtas ur Boverkets oppna
    API for koordinaten; terrangtyp, hojd och topografi ar bedomningar
    som anvandaren maste gora sjalv (BFS 2024:6 tab. 4:4 och 38 §).
    """
    plats = c.setdefault("plats", {})
    hamtat = plats.setdefault("hamtat", {})
    vind = c["laster"]["vind"]

    if hamtat.get("S_0"):
        st.caption(f"**{plats.get('adress', 'Platsen')}** — hämtat "
                   f"{hamtat.get('hamtat_datum', '?')}: S_0 = "
                   f"{hamtat['S_0']} kN/m2, v_b = {hamtat.get('v_b', '?')} "
                   f"m/s (Boverket, BFS 2024:6 figur 4:2/4:3)")
    else:
        st.caption("Ingen plats hämtad — snölasten kommer från "
                   "[laster.sno].s_k i projektfilen.")

    with st.expander("Hämta för en annan plats"):
        k1, k2 = st.columns(2)
        N = k1.number_input("N (northing)", 6_100_000, 7_700_000,
                            int(plats.get("x_koord", 6_580_822)), 1)
        E = k2.number_input("E (easting)", 200_000, 950_000,
                            int(plats.get("y_koord", 674_032)), 1)
        hoh = st.number_input("Höjd över havet [m]", 0.0, 2500.0,
                              float(plats.get("hoh", 0.0)), 1.0,
                              help="Över 1 500 m gäller inte Boverkets "
                                   "karta (BFS 2024:6 4 kap. 30 §).")
        st.caption("SWEREF99 TM (EPSG:3006). Datat är Boverkets och får "
                   "hämtas per projekt — inte skördas i bulk.")
        if st.button("Hämta från Boverket"):
            import datetime

            import plats as P
            try:
                d = P.hamta(N, E, hoh=hoh,
                            datum=datetime.date.today().isoformat())
            except P.PlatsFel as fel:
                st.error(str(fel))
            except Exception as fel:                    # natverk
                st.error(f"Kunde inte nå Boverkets API: {fel}")
            else:
                plats.update(x_koord=d.N, y_koord=d.E, hoh=d.hoh)
                hamtat.update(S_0=d.S_0, v_b=d.v_b, apiversion=d.apiversion,
                              hamtat_datum=d.hamtat)
                st.success(f"S_0 = {d.S_0} kN/m2, v_b = {d.v_b} m/s")
                for a in d.anmarkningar:
                    st.info(a)
                st.code(d.som_toml(), language="toml")

    # Manuella varden bakom en expander (anvandarbeslut 2026-08-19,
    # mobilskarmen blev overlastad): normalvagen ar hamtade varden +
    # sammanfattningen nedanfor. Terrangtypen ar fortfarande DIN
    # bedomning -- den ligger har for att skarmen ska vara ren, inte
    # for att den ar oviktig.
    with st.expander("Manuella värden: snö, vind och terräng"):
        c["laster"]["sno"]["s_k"] = st.number_input(
            "Snölast S_0 på mark [kN/m2]", 0.0, 8.0,
            float(c["laster"]["sno"].get("s_k", 0.0)), 0.1,
            help="0 = använd det hämtade värdet. Ett värde här "
                 "överstyr.")

        terr = list(material.terrangtyper())
        vind["terrangtyp"] = st.selectbox(
            "Terrängtyp", terr,
            format_func=lambda t: material.terrangtyper()[t]["namn"],
            index=_index(terr, str(vind.get("terrangtyp", "III"))),
            help="BFS 2024:6 tab. 4:4. Valet är riktningsberoende och "
                 "är DIN bedömning -- ingen datakälla avgör det.")
        k3, k4 = st.columns(2)
        vind["referenshojd"] = k3.number_input(
            "Referenshöjd z [m]", 1.0, 100.0,
            float(vind.get("referenshojd", 6.0)), 0.5)
        vind["topografifaktor"] = k4.number_input(
            "Topografifaktor c_0", 0.5, 2.0,
            float(vind.get("topografifaktor", 1.0)), 0.05,
            help="1,0 om topografin inte behöver beaktas (38 §).")
        vind["q_p"] = st.number_input(
            "Vind q_p [kN/m2]", 0.0, 2.5,
            float(vind.get("q_p", 0.0)), 0.05,
            help="0 = räkna ur v_b enligt BFS 2024:6 38 §. Ett värde "
                 "här överstyr. c_pe redigeras i projektfilen.")
    try:
        S_0, q_p, _ = berakning.lastforutsattningar(c)
        st.caption(f"Ger S_0 = {S_0:.2f} kN/m2 och q_p = {q_p:.3f} kN/m2")
    except ValueError as fel:
        st.warning(str(fel))


def pct(u):
    """Utnyttjande som procent -- VISNING, kvoterna raknas ororda."""
    return f"{u * 100:.0f} %"


def _index(lista, varde):
    try:
        return lista.index(varde)
    except ValueError:
        return 0


def _balkindex(balkar, namn):
    """Alternativen ar Balk-objekt; projektfilen anger balken med namn."""
    for i, b in enumerate(balkar):
        if b.namn == namn:
            return i
    return 0


# ---------------------------------------------------------------------------
# Redovisningen
# ---------------------------------------------------------------------------

def visa_sammanfattning(res):
    balk_u = res.varsta_balkkontroll
    a, b, c, d, e = st.columns(5)
    a.metric("Värsta utnyttjande", pct(res.varsta_utnyttjande),
             delta="OK" if res.haller else "EJ OK",
             delta_color="normal" if res.haller else "inverse",
             help="Balk, nockförband och nedböjning. Upplaget "
                  "redovisas separat och styr inte bedömningen.")
    b.metric("Balken", pct(balk_u.utnyttjande), help=balk_u.namn)
    c.metric("Nockförbandet", pct(res.forband_utnyttjande),
             help=f"{res.nocktyp} nock. Största av handbokens "
                  f"interaktion (utan V) och gruppkontrollerna.")
    u_upl = max((k.utnyttjande for k in res.upplag_kontroller), default=0.0)
    d.metric("Upplaget", pct(u_upl),
             help="ETA ekv. 3-5. Redovisas separat: styrs av "
                  "upplagslängd/förstärkning, inte av balkvalet, och "
                  "ingår inte i 'Värsta utnyttjande'.")
    u_nb = max((k.utnyttjande for k in res.nedbojning.kontroller),
               default=0.0)
    e.metric("Nedböjning", pct(u_nb), help=res.nedbojning.krav_namn)
    st.caption(f"{len(res.snittkrafter)} lastfall provade "
               f"({len(res.snofall)} snöfall x {len(res.vindfall)} vindfall "
               f"+ fallen utan vind, över alla kombinationer)."
               + (f" Nockfjäder K_u = {res.K_r['K_u']:.0f} kNm/rad."
                  if res.K_r else " Nocken räknas helt styv."))
    for v in res.varningar:
        st.warning(v, icon=":material/warning:")


def visa_ritningar(res, cfg):
    """
    EN 3D-modell i stallet for tre flikar (anvandarbeslut 2026-08-19):
    hela takstolen och nockdetaljen ar samma modell i tva vyer, och
    tvarsnittets innehall (skivor, indrag, spikdjup) syns direkt i 3D.
    Geometrin kommer ur ritning3d.geometri() -- samma koordinater som
    berakningen -- och produktionstabellerna ur SAMMA anrop.
    """
    st.subheader("Modell")
    kol_vy, kol_k1, kol_k2, kol_txt = st.columns(
        [3, 1.2, 1.2, 2], vertical_alignment="bottom")
    vy = kol_vy.radio("Vy", ["Nockdetalj", "Hela takstolen"],
                      horizontal=True, label_visibility="collapsed")
    visa_spik = kol_k1.toggle("Mått spikmönster", value=True,
                              help="Rutnätet, c/c och linjeavstånden.")
    visa_skiva = kol_k2.toggle("Mått skivor", value=True,
                               help="Skivornas kantmått med "
                                    "utdragslinjer.")
    textstorlek = kol_txt.slider("Textstorlek mått", 8, 24, 11,
                                 help="Gäller måttexterna i modellen. "
                                      "Vyknapparna i figuren (Fram/Sida/"
                                      "Topp) ger ortografiska vyer där "
                                      "måtten läses som på ritning.")
    detalj = vy == "Nockdetalj"
    # components.html i stallet for st.plotly_chart: bara sa kan
    # scrollzoomen dampas (ritning3d.LUGN_ZOOM). plotly.js laddas fran
    # appens egen statiska mapp, inte fran nagot CDN.
    import streamlit.components.v1 as components
    _pjs = Path(__file__).parent / "static" / "plotly.min.js"
    components.html(
        ritning3d.som_html(
            ritning3d.modell(res, cfg, detalj=detalj,
                             textstorlek=textstorlek,
                             visa_spikmatt=visa_spik,
                             visa_skivmatt=visa_skiva),
            plotlyjs="/app/static/plotly.min.js" if _pjs.exists()
            else True),
        height=590)
    fb = cfg["forband"]
    st.caption(
        f"**Skivor:** 2 x {fb['skiva_t']:.0f} mm {res.skivmaterial.namn}. "
        f"Skivlängderna är MINIMIMÅTT ur spikbildens utbredning plus "
        f"kantavstånd 15d = a3t (EN 1995-1-1 tab. 8.2; minst en "
        f"skivände är belastad i varje momentstyv körning) -- skivans "
        f"längd är inte en indata i modellen. Spik slås från BÅDA sidor "
        f"med sina verkliga längder, och sida -Y är förskjuten "
        f"{fb.get('sidoforskjutning', 0.0):.1f} x c/c från fogen så att "
        f"spik från motstående sidor inte kolliderar -- beräkning, "
        f"modell och CSV räknar på de verkliga lägena.")
    st.caption(
        "Livet är indraget från flänssidorna och livförstärkningen "
        "fyller indragningen -- först då ligger balksidan plan så "
        "att den utanpåliggande skivan bär mot BÅDA flänsarna. Det "
        "är också därför livgruppens spik går genom liv (två "
        "skjuvsnitt) medan flänsgruppens går in i flänsen (ett).")

    geo = ritning3d.geometri(res, cfg, detalj=True)
    with st.expander("Produktionsdata: skivor och spikbild"):
        st.markdown("**Skivor** (bbox = omskrivande rektangel). "
                    "Kantlängderna står längs vänster halvas kanter i "
                    "modellen (höger är spegelvänd) plus urtagets djup "
                    "vid mittdalen: kapa råvaran efter bbox, märk "
                    "kantlängderna, klart. CSV:n har alla hörn både i "
                    "modellens koordinater och från skivans nedre "
                    "vänstra bbox-hörn.")
        st.dataframe(
            [{"Skiva": sk["namn"], "Antal": sk["antal"],
              "Tjocklek [mm]": sk["tjocklek"],
              "Höjd [mm]": sk["hojd"],
              "Längd x höjd (bbox) [mm]":
                  f"{sk['bbox_langd']:.0f} x {sk['bbox_hojd']:.0f}"}
             for sk in geo["skivor"]], hide_index=True,
            width="stretch")
        cc = cfg["forband"]["cc_forbindare"]
        fs_andel = cfg["forband"].get("sidoforskjutning", 0.0)
        st.markdown(f"**Spikrutnätet** -- hela bilden ligger på ETT "
                    f"rutnät, ankrat i en punkt som går att KÄNNA på "
                    f"takstolen: REFERENSLINJEN (heldragen i modellen) "
                    f"går genom vinkeln mellan undre flänsarna, "
                    f"vinkelrätt mot balkaxeln. Övriga TVÄRLINJER "
                    f"ligger n x {cc:.0f} mm från den (tvärlinje nr 0 = "
                    f"referenslinjen, negativa mot fogen), och "
                    f"KRITLINJERNA parallella med skivkanten på "
                    f"avstånden 'fran_overkant_mm'. Sida -Y: förskjut "
                    f"{fs_andel * cc:.1f} mm från fogen. Spika "
                    f"korsningarna: börja på 'tvarlinje_nr' och ta "
                    f"'antal_per_halva' korsningar utåt. Halvorna är "
                    f"spegelvända.")
        st.dataframe(geo["spiklinjer"], hide_index=True,
                     width="stretch", height=260)
        st.markdown(f"**Spikkoordinater** ({len(geo['spiktabell'])} st, "
                    f"för maskinbearbetning). X längs spännvidden från "
                    f"stötfogen, Z lodrätt från balkaxeln vid fogen.")
        st.dataframe(geo["spiktabell"], hide_index=True,
                     width="stretch", height=200)
        rader = ["skiva;grupp;sida;x_mm;z_mm;spik;langd_mm"]
        rader += [f"{r['skiva']};{r['grupp']};{r['sida']};{r['x_mm']};"
                  f"{r['z_mm']};{r['spik']};{r['langd_mm']}"
                  for r in geo["spiktabell"]]
        # x_rel/z_rel: fran skivans nedre vanstra bbox-horn -- samma
        # koordinater som visas vid hornen i modellen (utmatning pa
        # rektangular rava). x_mm/z_mm ar modellens system.
        horn = ["skiva;horn;x_mm;z_mm;x_rel;z_rel"]
        for sk in geo["skivor"]:
            x0 = min(px for px, _ in sk["horn"])
            z0 = min(pz for _, pz in sk["horn"])
            horn += [f"{sk['namn']};{n + 1};{p[0]:.1f};{p[1]:.1f};"
                     f"{p[0] - x0:.1f};{p[1] - z0:.1f}"
                     for n, p in enumerate(sk["horn"])]
        linjerad = ["skiva;grupp;sida;fran_overkant_mm;"
                    "forsta_fran_fog_mm;delning_mm;antal_per_halva"]
        linjerad += [f"{r['skiva']};{r['grupp']};{r['sida']};"
                     f"{r['fran_overkant_mm']};{r['forsta_fran_fog_mm']};"
                     f"{r['delning_mm']};{r['antal_per_halva']}"
                     for r in geo["spiklinjer"]]
        k1, k2, k3 = st.columns(3)
        k1.download_button("Spiklinjer (CSV)",
                           "\n".join(linjerad).encode("utf-8"),
                           "spiklinjer.csv", "text/csv")
        k2.download_button("Spikkoordinater (CSV)",
                           "\n".join(rader).encode("utf-8"),
                           "spikbild.csv", "text/csv")
        k3.download_button("Skivkontur (CSV)",
                           "\n".join(horn).encode("utf-8"),
                           "skivkontur.csv", "text/csv")



def visa_balken(res):
    bs = res.balksnitt
    st.subheader(f"Balken - {res.balk.namn}")
    st.caption(f"Värsta snittet **{bs.s:.2f} m från takfoten** "
               f"({bs.sparre} sparre) i {bs.kombination}, {bs.snofall}, "
               f"vind: {bs.vindfall} - k_mod för {bs.varaktighet} last. "
               f"M = {bs.M:.2f} kNm, N = {bs.N:.2f} kN, V = {bs.V:.2f} kN. "
               f"Knäcklängd {res.L_ef:.2f} m.")
    st.dataframe(
        [{"Kontroll": k.namn,
          "E_d": round(k.E_d, 2) if k.E_d is not None else None,
          "R_d": round(k.R_d, 2) if k.R_d is not None else None,
          "Utnyttjande": round(k.utnyttjande, 3),
          "": "OK" if k.ok else "EJ OK",
          "Referens": k.referens} for k in res.balkkontroller],
        hide_index=True, width="stretch")
    anm = [a for k in res.balkkontroller for a in k.anmarkningar]
    if anm:
        with st.expander("Noteringar till balkkontrollen"):
            for a in anm:
                st.markdown(f"- {a}")


def visa_upplag_nedbojning(res):
    v, h = st.columns(2)
    with v:
        st.subheader("Upplag vid takfot")
        for k in res.upplag_kontroller:
            st.markdown(f"**{k.namn}**: {k.formel} -> "
                        f"**{k.utnyttjande:.3f}** "
                        f"{'OK' if k.ok else ':red[EJ OK]'}  \n"
                        f"_{k.referens}_")
            for a in k.anmarkningar:
                st.caption(f"- {a}")
        st.markdown(f"Horisontalkraft i väggkrön: "
                    f"**H = {res.H_takfot:.2f} kN** per takstol.")
    with h:
        nb = res.nedbojning
        st.subheader(f"Nedböjning ({nb.krav_namn})")
        st.dataframe(
            [{"Kontroll": k.namn, "u [mm]": round(k.E_d, 1),
              "Gräns [mm]": round(k.R_d, 1),
              "Utnyttjande": round(k.utnyttjande, 3),
              "": "OK" if k.ok else "EJ OK"} for k in nb.kontroller],
            hide_index=True, width="stretch")
        st.caption(f"Dimensionerande fall: {nb.fall_fin}. "
                   f"Skjuvdeformationens andel av u_fin: "
                   f"{nb.skjuvandel_fin:.0%}.")
        for a in nb.anmarkningar:
            st.caption(f"- {a}")


def visa_forband(res):
    d, k = res.dimensionerande, res.kontroll
    st.subheader("Nockförband (momentstyv)")
    st.caption(f"Dimensionerande: {d.kombination}, {d.snofall}, vind: "
               f"{d.vindfall} - k_mod för {d.varaktighet} last. "
               f"Skiva: {res.skivmaterial.namn}.")


    v, h = st.columns(2)
    with v:
        st.markdown("**Förbindarkapacitet** (EN 1995-1-1 8.2.2)")
        for gr in res.grupper:
            kap = gr.kapacitet
            with st.container(border=True):
                st.markdown(
                    f"**{gr.namn}** - {gr.forbindare.namn}  \n"
                    f"F_v,Rk = **{kap.F_v_Rk_kN:.3f} kN/snitt** "
                    f"({kap.brottmod}) -> F_v,Rd = {gr.F_v_Rd:.3f} kN  \n"
                    f"{gr.n_snitt} snitt/förbindare, {gr.antal} st, "
                    f"M_Rd = {gr.grupp.M_Rd:.2f} kNm")
    with h:
        skivor = (res.skivor_i_planet if res.metod == "i_planet"
                  else res.skivor_handbok)
        st.markdown("**Skivor och kontroll**")
        st.dataframe(
            [{"Skiva": s.namn, "Uppbyggnad": f"{s.n_skivor}x{s.t:.0f} mm",
              "h [mm]": round(s.h), "M_d [kNm]": round(s.M_d, 2)}
             for s in skivor], hide_index=True, width="stretch")
        st.markdown(f"M_Rd = min({k.M_plywood:.2f} ; "
                    f"{k.M_forbindare:.2f}) = **{k.M_Rd:.2f} kNm** "
                    f"({k.dimensionerande} dimensionerar), "
                    f"utnyttjande **{k.utnyttjande:.3f}**")
        if res.bada_metoderna_gar:
            hb = res.kontroll_handbok
            st.info(f"Med handbokens f_m: M_Rd = {hb.M_Rd:.2f} kNm, "
                    f"utnyttjande {hb.utnyttjande:.3f}.",
                    icon=":material/compare_arrows:")


def visa_snittkrafter(res):
    with st.expander(f"Snittkrafter i nocken - alla "
                     f"{len(res.snittkrafter)} fall"):
        d = res.dimensionerande
        st.dataframe(
            [{"Kombination": s.kombination, "Snöfall": s.snofall,
              "Vind": s.vindfall, "k_mod för": s.varaktighet,
              "M [kNm]": round(s.M, 2), "N [kN]": round(s.N, 2),
              "V [kN]": round(s.V, 2), "Dim.": "x" if s is d else ""}
             for s in res.snittkrafter],
            hide_index=True, width="stretch")


def visa_verktyg(cfg):
    st.subheader("Verktyg")
    v = st.container()
    with v:
        if st.button("Föreslå balk och spikning",
                     help="Provar HELA biblioteket (alla 72 balkar) i "
                          "stigande höjd och redovisar samtliga -- "
                          "sidopanelens serie- och livval ignoreras "
                          "här med flit, så att inget alternativ döljs."):
            c = copy.deepcopy(cfg)
            c["geometri"]["balk"] = ""
            c.setdefault("dimensionering", {})
            c["dimensionering"]["foresla_serie"] = ""
            c["dimensionering"]["foresla_liv"] = ""
            with st.spinner("Provar alla 72 balkar..."):
                f = dimensionera.foresla(c)
            st.dataframe(
                [{"Balk": k.namn, "Balken": round(k.balk_u, 3),
                  "Förband": round(k.forband_u, 3),
                  "Upplag": round(k.upplag_u, 3),
                  "Nedböjn.": round(k.nedbojning_u, 3),
                  "Status": "HÅLLER" if k.haller
                  else f"styrs av {k.styrande}"}
                 for k in f.kandidater], hide_index=True, width="stretch")
            if f.vald and not f.spik.get("hittad"):
                st.warning(f.spik.get("kommentar", "Ingen spikning hittad."),
                           icon=":material/warning:")
            if f.vald:
                s = f.spik
                (st.success if s.get("hittad") else st.info)(
                    f"Vald: **{f.vald}**"
                    + (f", minsta spikning "
                       f"{s.get('kolumner_flans', 1)}x{s['rader_flans']} "
                       f"kolumner x rader fläns, "
                       f"{s['kolumner_liv']}x{s['rader_liv']} liv, "
                       f"mönster '{s.get('spikmonster', 'rutnat')}' "
                       f"({s['totalt']} st, verifierat utnyttjande "
                       f"{s.get('utnyttjande_verifierad', 0):.3f})"
                       if s.get("hittad") else ""))
            for a in f.anmarkningar:
                st.info(a)


def main():
    st.set_page_config(page_title="Takstol i lättbalk", layout="wide",
                       page_icon=":material/architecture:")
    st.title("Sadeltakstol i lättbalk")
    if HOSTAT:
        st.caption(
            "Den här instansen kör på en delad server: det du matar in "
            "behandlas där och sessionen sparas inte mellan besök. För "
            "full integritet (ingenting lämnar datorn) — kör appen "
            "lokalt enligt README.")
    st.caption("Balkdata ur Masonite Beams ETA 12/0018, skivor ur "
               "EN 12369-1, förbindare ur EN 1995-1-1 8.2.2. "
               "Lastkombinationer enligt BFS 2024:6. Nockförband enligt "
               "The I-joist Handbook 5.3.4.1 (momentstyvt) eller 5.3.7 "
               "(ledat). Upplag enligt ETA ekv. 3-5.")

    if "cfg" not in st.session_state:
        cfg0, sparad, steg0 = las_startcfg()
        # typvalet ar borttaget -- aldre autospar kan saga ledad
        cfg0.setdefault("system", {})["nock_styv"] = True
        st.session_state.cfg = cfg0
        st.session_state["_autospar_tid"] = sparad
        st.session_state["_startsteg"] = steg0

    stegval = ["1. Plats, laster och typ", "2. Mått, ritning och resultat"]
    steg = st.radio("Steg", stegval, horizontal=True,
                    index=0 if st.session_state.get("_startsteg", 1) == 1
                    else 1,
                    label_visibility="collapsed", key="stegradio")
    if st.session_state.get("_autospar_tid"):
        v, h = st.columns([5, 1])
        v.caption(f"Senaste inmatningen återupptogs (sparad "
                  f"{st.session_state['_autospar_tid']}). Projektfilen "
                  f"är orörd.")
        if h.button("Läs om projektfilen",
                    help="Glömmer autosparet och läser in "
                         "input/projekt.toml på nytt."):
            import copy
            SENASTE.unlink(missing_ok=True)
            st.session_state.cfg = copy.deepcopy(las_grundcfg())
            st.session_state["_autospar_tid"] = None
            st.session_state.pop("_senast_sparat", None)
            st.session_state["_hoppa_over_autospar"] = True
            st.rerun()
    st.divider()

    if steg.startswith("1"):
        st.session_state.cfg = steg1_forutsattningar(st.session_state.cfg)
        spara_senaste(st.session_state.cfg, 1)
        st.divider()
        st.info("Gå vidare till steg 2 för måtten, ritningarna och "
                "resultaten.", icon=":material/arrow_forward:")
        return

    cfg = steg2_matt(st.session_state.cfg)
    st.session_state.cfg = cfg
    spara_senaste(cfg, 2)
    try:
        res = berakning.kor(cfg)
    except (ValueError, KeyError) as fel:
        st.error(str(fel).strip('"'), icon=":material/error:")
        st.caption("Ändra valen ovan eller i steg 1. Felet kommer från "
                   "materialbiblioteket eller beräkningen.")
        return

    st.divider()
    visa_ritningar(res, cfg)
    st.divider()
    visa_sammanfattning(res)
    visa_balken(res)
    visa_upplag_nedbojning(res)
    visa_forband(res)
    visa_snittkrafter(res)
    with st.expander("Antaganden", expanded=False):
        for a in res.antaganden:
            st.markdown(f"- {a}")
    st.divider()
    visa_verktyg(cfg)
    st.caption("Underlag, inte konstruktionshandling. Se README för vad "
               "som ligger utanför: vippning utöver ETA tab. 19:s "
               "sidostödsvillkor, hålskärningar, brand, andra "
               "takstolstyper än sadeltakstolen.")


if __name__ == "__main__":
    main()
