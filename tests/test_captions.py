"""Legendas ASS: cor, tempo, agrupamento e offset da timeline de saída."""
import json
from pathlib import Path

import pytest
from conftest import load

captions = load("captions")


class TestCor:
    def test_hex_vira_bgr(self):
        # ASS inverte os canais: #RRGGBB vira &HAABBGGRR
        assert captions.hex_to_ass("#FF0000") == "&H000000FF"   # vermelho
        assert captions.hex_to_ass("#0000FF") == "&H00FF0000"   # azul
        assert captions.hex_to_ass("#FFFFFF") == "&H00FFFFFF"

    def test_aceita_forma_curta_e_sem_cerquilha(self):
        assert captions.hex_to_ass("#FFF") == captions.hex_to_ass("#FFFFFF")
        assert captions.hex_to_ass("FF5A00") == captions.hex_to_ass("#FF5A00")

    def test_alpha(self):
        assert captions.hex_to_ass("#FFFFFF", alpha=128) == "&H80FFFFFF"

    def test_cor_invalida_levanta(self):
        with pytest.raises(ValueError):
            captions.hex_to_ass("#GGGGGG00")


class TestTempo:
    def test_formato_centesimos(self):
        # ASS usa centésimos, não milésimos — errar isso desloca tudo em 10x
        assert captions.ass_time(0) == "0:00:00.00"
        assert captions.ass_time(1.5) == "0:00:01.50"
        assert captions.ass_time(3661.23) == "1:01:01.23"

    def test_negativo_vira_zero(self):
        assert captions.ass_time(-5) == "0:00:00.00"


def w(text, start, end, speaker="S0"):
    return captions.Word(text=text, start=start, end=end, speaker=speaker)


class TestAgrupamento:
    def test_quebra_por_contagem(self):
        words = [w(f"p{i}", i * 0.3, i * 0.3 + 0.25) for i in range(6)]
        chunks = captions.chunk_words(words, max_words=2)
        assert len(chunks) == 3
        assert all(len(c.words) == 2 for c in chunks)

    def test_quebra_em_silencio_longo(self):
        words = [w("um", 0.0, 0.3), w("dois", 2.0, 2.3)]
        chunks = captions.chunk_words(words, max_words=10)
        assert len(chunks) == 2

    def test_quebra_na_troca_de_falante(self):
        words = [w("oi", 0.0, 0.3, "S0"), w("tudo", 0.35, 0.6, "S1")]
        chunks = captions.chunk_words(words, max_words=10)
        assert len(chunks) == 2

    def test_quebra_em_pontuacao_final(self):
        words = [w("acabou.", 0.0, 0.4), w("comeca", 0.45, 0.8)]
        chunks = captions.chunk_words(words, max_words=10)
        assert len(chunks) == 2

    def test_virgula_nao_quebra(self):
        words = [w("ola,", 0.0, 0.4), w("mundo", 0.45, 0.8)]
        assert len(captions.chunk_words(words, max_words=10)) == 1


class TestHold:
    def test_bloco_curto_e_estendido(self):
        chunks = captions.chunk_words([w("oi", 0.0, 0.12)], max_words=2)
        timed = captions.hold_chunks(chunks, min_dur=0.5)
        _, t_in, t_out = timed[0]
        assert t_out - t_in >= 0.5

    def test_nao_invade_o_proximo_bloco(self):
        words = [w("um", 0.0, 0.1), w("dois", 2.0, 2.4)]
        chunks = captions.chunk_words(words, max_words=1)
        timed = captions.hold_chunks(chunks, min_dur=0.5, max_hold=5.0)
        assert timed[0][2] <= timed[1][1]


class TestEventos:
    def _words(self):
        return [w("um", 0.0, 0.3), w("dois", 0.35, 0.7), w("tres", 0.75, 1.1)]

    def test_karaoke_emite_kf(self):
        st = captions.STYLES["karaoke"]
        ass = captions.build_ass(self._words(), st)
        assert r"\kf" in ass
        assert ass.count("Dialogue:") == 1      # um evento por bloco

    def test_pop_emite_um_evento_por_palavra(self):
        st = captions.STYLES["pop"]
        ass = captions.build_ass(self._words(), st)
        assert ass.count("Dialogue:") == 3
        assert r"\t(0,90,\fscx100\fscy100)" in ass

    def test_hormozi_destaca_a_palavra_corrente(self):
        st = captions.STYLES["hormozi"]
        ass = captions.build_ass(self._words(), st)
        accent = captions.hex_to_ass(st.accent_color)
        # cada evento mostra o bloco inteiro, com uma palavra na cor de destaque
        assert ass.count("Dialogue:") == 3
        assert accent in ass

    def test_doc_nao_usa_caixa_alta(self):
        st = captions.STYLES["doc"]
        ass = captions.build_ass([w("Olá", 0.0, 0.4)], st)
        assert "Olá" in ass and "OLÁ" not in ass

    def test_cabecalho_usa_a_resolucao_real(self):
        ass = captions.build_ass(self._words(), captions.STYLES["clean"], 1080, 1920)
        assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
        assert ass.count("Style: Default") == 1
        assert "[Events]" in ass

    def test_wrapstyle_permite_quebra(self):
        # WrapStyle 2 DESLIGA a quebra e o texto sai pelas bordas do quadro
        ass = captions.build_ass(self._words(), captions.STYLES["hormozi"])
        assert "WrapStyle: 0" in ass
        assert "WrapStyle: 2" not in ass

    def test_fonte_escala_com_a_altura(self):
        st = captions.STYLES["hormozi"]
        hd = captions.build_ass(self._words(), st, 1920, 1080)
        uhd = captions.build_ass(self._words(), st, 3840, 2160)

        def fontsize(ass):
            linha = [l for l in ass.splitlines() if l.startswith("Style: Default")][0]
            return int(linha.split(",")[2])

        # mesma proporção de tela em qualquer entrega
        assert fontsize(uhd) == pytest.approx(fontsize(hd) * 2, rel=0.02)


class TestMargemPorAspecto:
    """Safe-zone depende do aspecto: 9:16 tem UI embaixo, 16:9 não tem."""

    def test_vertical_reserva_muito_mais_que_horizontal(self):
        vert = captions.margin_for_aspect(1080, 1920)
        horiz = captions.margin_for_aspect(1920, 1080)
        assert vert > horiz * 2

    def test_vertical_cobre_a_ui_das_redes(self):
        # a UI de TikTok/Reels/Shorts come ~25-30% da base
        assert captions.margin_for_aspect(1080, 1920) >= 0.15

    def test_horizontal_nao_joga_legenda_para_o_meio(self):
        assert captions.margin_for_aspect(1920, 1080) <= 0.10

    def test_quadrado_e_4x5_ficam_entre_os_dois(self):
        horiz = captions.margin_for_aspect(1920, 1080)
        vert = captions.margin_for_aspect(1080, 1920)
        for w, h in ((1080, 1080), (1080, 1350)):
            m = captions.margin_for_aspect(w, h)
            assert horiz <= m <= vert

    def test_margem_aplicada_no_cabecalho(self):
        words = [w("um", 0.0, 0.3)]
        ass = captions.build_ass(words, captions.STYLES["hormozi"], 1080, 1920)
        linha = [l for l in ass.splitlines() if l.startswith("Style: Default")][0]
        margin_v = int(linha.split(",")[21])
        assert margin_v == round(0.18 * 1920)


class TestQuebraDeLinha:
    def test_bloco_curto_fica_em_uma_linha(self):
        assert captions.balance_lines(["um", "dois"], max_chars=22) == [[0, 1]]

    def test_bloco_longo_vira_duas_linhas(self):
        palavras = ["RESULTADO", "COMPLETAMENTE", "DIFERENTE"]
        linhas = captions.balance_lines(palavras, max_chars=18)
        assert len(linhas) == 2

    def test_linhas_ficam_equilibradas(self):
        palavras = ["A", "B", "CCCCCCCCCC", "DDDDDDDDDD"]
        linhas = captions.balance_lines(palavras, max_chars=12)
        tam = [sum(len(palavras[i]) for i in linha) for linha in linhas]
        assert abs(tam[0] - tam[1]) < sum(tam) / 2

    def test_palavra_unica_nunca_quebra(self):
        assert captions.balance_lines(["SUPERCALIFRAGILISTICO"], max_chars=5) == [[0]]

    def test_quebra_entra_no_ass_como_N(self):
        palavras = [w(t, i * 0.4, i * 0.4 + 0.35)
                    for i, t in enumerate(["RESULTADO", "COMPLETAMENTE", "DIFERENTE"])]
        ass = captions.build_ass(palavras, captions.STYLES["hormozi"])
        assert r"\N" in ass


class TestOffsetDaTimeline:
    """A matemática que mantém legenda alinhada depois do concat (Regra Dura 5)."""

    def _setup(self, tmp_path, speed=None):
        tdir = tmp_path / "transcripts"
        tdir.mkdir()
        transcript = {"words": [
            {"text": "alfa", "start": 10.0, "end": 10.4, "type": "word", "speaker_id": "S0"},
            {"text": "beta", "start": 10.5, "end": 10.9, "type": "word", "speaker_id": "S0"},
            {"text": "gama", "start": 30.0, "end": 30.4, "type": "word", "speaker_id": "S0"},
        ]}
        (tdir / "A.json").write_text(json.dumps(transcript))
        seg = {"source": "A", "start": 10.0, "end": 11.0}
        if speed:
            seg["speed"] = speed
        return {"sources": {"A": str(tmp_path / "A.mp4")}, "ranges": [seg]}

    def test_palavra_e_remapeada_para_a_saida(self, tmp_path):
        edl = self._setup(tmp_path)
        words = captions.collect_words_from_edl(edl, tmp_path)
        assert len(words) == 2                       # 'gama' está fora do range
        assert words[0].start == pytest.approx(0.0)  # 10.0 - 10.0 + 0
        assert words[1].start == pytest.approx(0.5)

    def test_speed_comprime_o_tempo_da_legenda(self, tmp_path):
        edl = self._setup(tmp_path, speed=2.0)
        words = captions.collect_words_from_edl(edl, tmp_path)
        # a 2x, a palavra que começava em 0.5s na fonte aparece em 0.25s na saída
        assert words[1].start == pytest.approx(0.25)

    def test_segundo_segmento_recebe_o_offset_do_primeiro(self, tmp_path):
        edl = self._setup(tmp_path)
        edl["ranges"].append({"source": "A", "start": 30.0, "end": 30.5})
        words = captions.collect_words_from_edl(edl, tmp_path)
        assert words[-1].text == "gama"
        # primeiro segmento dura 1.0s, então 'gama' (30.0) cai em 1.0s na saída
        assert words[-1].start == pytest.approx(1.0)

    def test_transcript_ausente_nao_quebra(self, tmp_path, capsys):
        edl = {"sources": {"B": str(tmp_path / "B.mp4")},
               "ranges": [{"source": "B", "start": 0.0, "end": 1.0}]}
        (tmp_path / "transcripts").mkdir()
        assert captions.collect_words_from_edl(edl, tmp_path) == []
