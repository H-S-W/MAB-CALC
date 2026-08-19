#!/usr/bin/env python3
"""
Kor hela kedjan fran kommandoraden och skriver ut resultatet.

    python run.py [input/projekt.toml]
    python run.py --foresla [input/projekt.toml]   sok balk och spikning
    python run.py --jamfor [input/projekt.toml]    momentstyv mot ledad nock

All berakning ligger i src/. Den har filen stallar bara upp resultatet.
Webbgranssnittet i app.py laser samma resultat.
"""

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import berakning                                    # noqa: E402
from forband import rapport                         # noqa: E402


def skriv(res):
    b = res.balk
    print(f"BALK  {b.namn}  (serie {b.serie}, {b.liv}-liv, h = {b.h:.0f} mm)")
    print(f"      M_k = {b.M_k} kNm   V_k = {b.V_k} kN   EI = {b.EI} kNm2   "
          f"GA = {b.GA} kN   EA = {b.EA(res.flanskvalitet):.0f} kN "
          f"({res.flanskvalitet})")
    if res.K_r:
        print(f"      Nockfjäder: K_ser = {res.K_r['K_ser']:.0f}, "
              f"K_u = {res.K_r['K_u']:.0f} kNm/rad")

    print(f"\nEgentyngd: {res.g_k:.3f} kN/m2 horisontalprojektion "
          f"-> {res.q_g:.3f} kN/m per takstol")
    print(f"Snölastfall: {len(res.snofall)}   Vindfall: {len(res.vindfall)}"
          f"   Provade fall totalt: {len(res.snittkrafter)}")

    print(f"\n{'=' * 72}\nSAMMANFATTNING\n{'=' * 72}")
    vb = res.varsta_balkkontroll
    rader = [("Balken", vb.utnyttjande, vb.namn),
             ("Nockförbandet", res.forband_utnyttjande,
              f"{res.nocktyp} nock")]
    for k in res.upplag_kontroller:
        rader.append((k.namn, k.utnyttjande, ""))
    for k in res.nedbojning.kontroller:
        rader.append((k.namn, k.utnyttjande, k.formel.split("(")[-1][:-1]))
    for namn, u, info in rader:
        flagga = "OK" if u <= 1.0 else "<< EJ OK >>"
        print(f"  {namn:<28} {u:7.3f}  {flagga:12} {info}")
    print(f"\n  TAKSTOLEN (balk+förband+nedböjning): "
          f"{'HÅLLER' if res.haller else 'HÅLLER INTE'} "
          f"(värsta utnyttjande {res.varsta_utnyttjande:.3f})")
    print(f"  UPPLAGET (redovisas separat):        "
          f"{res.upplag_utnyttjande:.3f} "
          f"{'OK' if res.upplaget_haller else '<< EJ OK >>'}  "
          f"-- styrs av L1/förstärkning, inte av balkvalet")

    bs = res.balksnitt
    print(f"\n{'=' * 72}\nBALKEN\n{'=' * 72}")
    print(f"Värsta snittet: {bs.s:.2f} m från takfoten på "
          f"{'vänster' if bs.sparre == 'vanster' else 'höger'} sparre")
    print(f"  {bs.kombination}, {bs.snofall}, vind: {bs.vindfall} "
          f"(k_mod för {bs.varaktighet})")
    print(f"  M = {bs.M:.2f} kNm   N = {bs.N:.2f} kN "
          f"({'drag' if bs.N >= 0 else 'tryck'})   V = {bs.V:.2f} kN   "
          f"Knäcklängd {res.L_ef:.2f} m")
    for k in res.balkkontroller:
        E = f"{k.E_d:.2f}" if k.E_d is not None else ""
        R = f"{k.R_d:.2f}" if k.R_d is not None else ""
        flagga = "OK" if k.ok else "<< EJ OK >>"
        print(f"  {k.namn:<32}{E:>9}{R:>9}{k.utnyttjande:>8.3f}   {flagga}")
        for a in k.anmarkningar:
            print(f"  {'':<32}- {a}")

    print(f"\n{'=' * 72}\nUPPLAG OCH HORISONTALKRAFT\n{'=' * 72}")
    for k in res.upplag_kontroller:
        flagga = "OK" if k.ok else "<< EJ OK >>"
        print(f"  {k.namn}: {k.formel}  ->  {k.utnyttjande:.3f}  {flagga}")
        print(f"    {k.referens}")
        for a in k.anmarkningar:
            print(f"    - {a}")
    print(f"  Horisontalkraft i väggkrön: H = {res.H_takfot:.2f} kN "
          f"per takstol")

    nb = res.nedbojning
    print(f"\n{'=' * 72}\nNEDBÖJNING (krav: {nb.krav_namn}, "
          f"L = {nb.L_sparre:.2f} m)\n{'=' * 72}")
    for k in nb.kontroller:
        flagga = "OK" if k.ok else "<< EJ OK >>"
        print(f"  {k.namn:<20} {k.formel}  ->  {k.utnyttjande:.3f}  "
              f"{flagga}   [{k.referens}]")
    print(f"  Skjuvdeformationens andel av u_fin: "
          f"{nb.skjuvandel_fin:.0%} (kryper med k_def "
          f"{'1,50' if res.balk.liv == 'osb' else '2,25'} mot böjningens "
          f"0,60)")
    for a in nb.anmarkningar:
        print(f"  - {a}")

    d = res.dimensionerande
    print(f"\n{'=' * 72}\nNOCKFÖRBAND ({res.nocktyp})\n{'=' * 72}")
    print(f"Dimensionerande: {d.kombination}, {d.snofall}, vind: "
          f"{d.vindfall} (k_mod för {d.varaktighet})")
    if res.nocktyp == "ledad":
        led = res.ledad
        print(f"  N = {d.N:.2f} kN  V = {d.V:.2f} kN  ->  "
              f"excentricitet e = {led.e:.0f} mm, M = {led.M:.2f} kNm")
        print(f"  Förbindare: F = {led.F:.3f} kN mot {led.F_Rd:.3f} kN  "
              f"->  {led.u_forbindare:.3f}")
        print(f"  Skiva skjuvning: {led.u_skiva_skjuv:.3f}   "
              f"Skiva böjning: {led.u_skiva_moment:.3f}")
        print(f"  ({led.metodnot})")
    else:
        for gr in res.grupper:
            k = gr.kapacitet
            print(f"  {gr.namn:<28} {gr.forbindare.namn}: F_v,Rk = "
                  f"{k.F_v_Rk_kN:.3f} kN/snitt ({k.brottmod}), "
                  f"{gr.n_snitt} snitt, {gr.antal} st")
        skivor = (res.skivor_i_planet if res.metod == "i_planet"
                  else res.skivor_handbok)
        print()
        riktning = (f"f_t,{res.skivmaterial.dragriktning} i planet"
                    if res.metod == "i_planet" else "handbokens f_m")
        print(rapport(f"KONTROLL ({riktning})",
                      skivor, [g.grupp for g in res.grupper], res.kontroll,
                      d.M, abs(d.N), d.V))
        if res.bada_metoderna_gar:
            h = res.kontroll_handbok
            print(f"\nMed handbokens f_m: M_Rd = {h.M_Rd:.2f} kNm, "
                  f"utnyttjande {h.utnyttjande:.3f} "
                  f"(dimensionerande metod: {res.kontroll.utnyttjande:.3f})")

    if res.varningar:
        print(f"\n{'=' * 72}\nVARNINGAR\n{'=' * 72}")
        for v in res.varningar:
            print(f"  ! {v}")
    print(f"\n{'=' * 72}\nANTAGANDEN\n{'=' * 72}")
    for a in res.antaganden:
        print(f"  - {a}")


def skriv_forslag(cfg):
    import dimensionera
    f = dimensionera.foresla(cfg)
    print(f"{'balk':8}{'balken':>9}{'förband':>9}{'upplag':>9}"
          f"{'nedböjn':>9}   status")
    for k in f.kandidater:
        flagga = "HÅLLER" if k.haller else f"styrs av {k.styrande}"
        print(f"{k.namn:8}{k.balk_u:9.3f}{k.forband_u:9.3f}"
              f"{k.upplag_u:9.3f}{k.nedbojning_u:9.3f}   {flagga}")
    print(f"\nVald balk: {f.vald or '(ingen kandidat håller)'}")
    if f.spik.get("hittad"):
        s = f.spik
        print(f"Minsta spikning: {s.get('kolumner_flans', 1)} kolumn(er) "
              f"x {s['rader_flans']} rader i fläns, "
              f"{s['kolumner_liv']}x{s['rader_liv']} i liv, "
              f"mönster '{s.get('spikmonster', 'rutnat')}' "
              f"({s['totalt']} förbindare, utnyttjande "
              f"{s['utnyttjande']:.3f}, verifierad: "
              f"{s.get('utnyttjande_verifierad', float('nan')):.3f})")
    elif f.vald:
        print(f"Spikning: {f.spik.get('kommentar', '')}")
    for a in f.anmarkningar:
        print(f"! {a}")


def skriv_jamforelse(cfg):
    resultat = berakning.jamfor_nock(cfg)
    print(f"{'':32}{'momentstyv':>12}{'ledad':>12}")
    styv, led = resultat["momentstyv"], resultat["ledad"]

    def rad(namn, f, fmt="{:.2f}"):
        print(f"{namn:<32}{fmt.format(f(styv)):>12}{fmt.format(f(led)):>12}")

    rad("Nockmoment M [kNm]", lambda r: r.dimensionerande.M)
    rad("M i värsta balksnittet [kNm]", lambda r: r.balksnitt.M)
    rad("Balkutnyttjande", lambda r: r.varsta_balkkontroll.utnyttjande,
        "{:.3f}")
    rad("Förbandsutnyttjande", lambda r: r.forband_utnyttjande, "{:.3f}")
    rad("Horisontalkraft H [kN]", lambda r: r.H_takfot)
    rad("u_fin [mm]", lambda r: next(
        (k.E_d for k in r.nedbojning.kontroller if "fin" in k.namn),
        float("nan")), "{:.1f}")
    rad("Upplag (redovisas separat)", lambda r: r.upplag_utnyttjande,
        "{:.3f}")
    rad("Håller (balk+förband+nedböjn.)", lambda r: r.haller, "{}")
    print("\nMed dragband eller vindsbjälklag som dragband behöver nocken "
          "sannolikt inte vara momentstyv alls -- se README.")


def main(argv):
    flaggor = [a for a in argv if a.startswith("--")]
    ovriga = [a for a in argv if not a.startswith("--")]
    path = ovriga[0] if ovriga else "input/projekt.toml"
    with open(path, "rb") as fh:
        cfg = tomllib.load(fh)

    if "--foresla" in flaggor:
        skriv_forslag(cfg)
    elif "--jamfor" in flaggor:
        skriv_jamforelse(cfg)
    else:
        skriv(berakning.kor(cfg))


if __name__ == "__main__":
    main(sys.argv[1:])
