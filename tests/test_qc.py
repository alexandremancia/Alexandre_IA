"""QC: fronteiras da timeline, parsing de legenda e colisão com overlay."""
import pytest
from conftest import load

qc = load("qc")


class TestFronteiras:
    def test_junções_e_duracao_total(self):
        edl = {"ranges": [{"start": 0, "end": 2}, {"start": 5, "end": 8}, {"start": 0, "end": 1}]}
        bounds, total = qc.edl_boundaries(edl)
        assert total == pytest.approx(6.0)
        assert bounds == [2.0, 5.0]      # o fim do arquivo não é junção

    def test_segmento_unico_nao_tem_juncao(self):
        bounds, total = qc.edl_boundaries({"ranges": [{"start": 0, "end": 4}]})
        assert bounds == []
        assert total == pytest.approx(4.0)

    def test_speed_encurta_a_duracao_esperada(self):
        edl = {"ranges": [{"start": 0, "end": 4, "speed": 2.0}]}
        _, total = qc.edl_boundaries(edl)
        assert total == pytest.approx(2.0)

    def test_edl_vazio(self):
        assert qc.edl_boundaries({"ranges": []}) == ([], 0.0)


class TestParsingDeTempo:
    def test_ass(self):
        assert qc.ass_secs("0:00:01.50") == pytest.approx(1.5)
        assert qc.ass_secs("1:01:01.23") == pytest.approx(3661.23)

    def test_srt(self):
        assert qc.srt_secs("00:00:01,500") == pytest.approx(1.5)
        assert qc.srt_secs("01:01:01,230") == pytest.approx(3661.23)


class TestSobreposicao:
    def test_janelas_que_se_cruzam(self):
        assert qc.overlaps((0, 2), (1, 3))

    def test_janelas_disjuntas(self):
        assert not qc.overlaps((0, 1), (2, 3))

    def test_encostadas_nao_sobrepoem(self):
        assert not qc.overlaps((0, 1), (1, 2))


class TestLegenda:
    def _ass(self, tmp_path, margin=346):
        p = tmp_path / "s.ass"
        p.write_text(
            "[Script Info]\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,Helvetica,18,&H00FFFFFF,&H00FF5A00,&H00000000,&H00000000,1,0,0,0,"
            f"100,100,0,0,1,2,0,2,60,60,{margin},1\n\n"
            "[Events]\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,OLA MUNDO\n"
            "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,SEGUNDA LINHA\n"
        )
        return p

    def test_le_margem_e_resolucao(self, tmp_path):
        margin, px, py = qc.parse_ass_geometry(self._ass(tmp_path, margin=346))
        assert margin == 346 and px == 1080 and py == 1920

    def test_le_janelas_de_tempo(self, tmp_path):
        assert qc.subtitle_times(self._ass(tmp_path)) == [(1.0, 3.0), (4.0, 6.0)]

    def test_srt_tambem(self, tmp_path):
        p = tmp_path / "s.srt"
        p.write_text("1\n00:00:01,000 --> 00:00:03,000\nOLA\n\n")
        assert qc.subtitle_times(p) == [(1.0, 3.0)]

    def test_overlay_sem_geometria_vira_aviso(self, tmp_path):
        sub = self._ass(tmp_path)
        edl = {"subtitles": str(sub),
               "overlays": [{"start_in_output": 1.5, "duration": 1.0}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert any(c.level == "warn" for c in checks)

    def test_overlay_com_geometria_declarada_passa(self, tmp_path):
        sub = self._ass(tmp_path)
        edl = {"subtitles": str(sub),
               "overlays": [{"start_in_output": 1.5, "duration": 1.0, "x": 0, "y": 100}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert all(c.level == "ok" for c in checks)

    def test_overlay_fora_da_janela_da_legenda_passa(self, tmp_path):
        sub = self._ass(tmp_path)
        edl = {"subtitles": str(sub),
               "overlays": [{"start_in_output": 7.0, "duration": 1.0}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert all(c.level == "ok" for c in checks)

    def test_margem_baixa_demais_avisa(self, tmp_path):
        sub = self._ass(tmp_path, margin=20)     # 1% de 1920
        edl = {"subtitles": str(sub), "overlays": [{"start_in_output": 1.5, "duration": 1.0, "y": 50}]}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert any("safe-zone" in c.name for c in checks if c.level == "warn")

    def test_margem_correta_para_vertical_nao_avisa(self, tmp_path):
        sub = self._ass(tmp_path, margin=346)    # 18% de 1920, o que o captions.py gera
        edl = {"subtitles": str(sub), "overlays": []}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert not any("safe-zone" in c.name for c in checks)


class TestSafeZoneRelativa:
    """Margem só quer dizer algo em relação ao PlayResY, nunca em pixels absolutos."""

    def test_piso_vertical_e_maior_que_horizontal(self):
        vert, _ = qc.min_margin_pct(1080, 1920)
        horiz, _ = qc.min_margin_pct(1920, 1080)
        assert vert > horiz

    def test_classifica_o_formato(self):
        assert qc.min_margin_pct(1080, 1920)[1] == "vertical"
        assert qc.min_margin_pct(1080, 1080)[1] == "quadrado"
        assert qc.min_margin_pct(1920, 1080)[1] == "horizontal"

    def test_mesma_margem_em_px_passa_ou_falha_conforme_a_altura(self):
        """346px é 18% em 1920 (ok) e 32% em 1080 (exagerado, mas nunca 'baixo')."""
        piso_v, _ = qc.min_margin_pct(1080, 1920)
        assert 346 / 1920 > piso_v
        piso_h, _ = qc.min_margin_pct(1920, 1080)
        assert 346 / 1080 > piso_h

    def test_legenda_ausente_no_disco_e_falha(self, tmp_path):
        edl = {"subtitles": str(tmp_path / "nao_existe.ass"), "overlays": []}
        checks = qc.check_caption_collision(edl, tmp_path, 10.0)
        assert any(c.level == "fail" for c in checks)


class TestDeteccaoDeEstalo:
    """Nível de salto NÃO distingue estalo de conteúdo; largura do pico distingue.

    Medido em emendas reais, janela de ±60ms:
        corte com fade 30ms   -42.7 dBFS, 2570 amostras no pico
        corte seco (estalo)   -24.3 dBFS,    3 amostras
        batida de bumbo        -4.0 dBFS,   16 amostras
        transiente de fala    -19.2 dBFS,   33 amostras

    O bumbo salta 20 dB MAIS alto que o estalo. Um limiar por nível marcaria
    toda música percussiva e deixaria o estalo passar.
    """
    import numpy as _np

    def _senoide(self, n=4800, freq=440, sr=48000, amp=0.5):
        import numpy as np
        return (amp * np.sin(2 * np.pi * freq * np.arange(n) / sr)).astype(np.float32)

    def test_sinal_continuo_nao_tem_pico_isolado(self):
        peak, width = qc.pop_score(self._senoide())
        assert not qc.is_pop(peak, width)

    def test_degrau_de_uma_amostra_e_estalo(self):
        import numpy as np
        y = self._senoide()
        y[2400:] += 0.4                      # descontinuidade entre dois samples
        peak, width = qc.pop_score(y)
        assert width <= 8
        assert qc.is_pop(peak, width)

    def test_transiente_com_envelope_nao_e_estalo(self):
        """Bumbo tem ataque E decaimento: nunca volta a zero de um sample para outro."""
        import numpy as np
        y = self._senoide(amp=0.1)
        n_a, n_d = 48, 900                        # 1ms de ataque, ~19ms de cauda
        ataque = np.linspace(0, 1, n_a) ** 2
        decaimento = np.exp(-np.linspace(0, 6, n_d))
        env = np.concatenate([ataque, decaimento]).astype(np.float32)
        golpe = env * np.sin(2 * np.pi * 60 * np.arange(len(env)) / 48000) * 0.9
        y[2400:2400 + len(golpe)] += golpe.astype(np.float32)
        peak, width = qc.pop_score(y)
        assert width > 8, f"transiente marcado como estalo (largura {width})"
        assert not qc.is_pop(peak, width)

    def test_transiente_alto_nao_mascara_estalo(self):
        """O bumbo salta mais alto que o estalo — por isso o critério não é nível."""
        import numpy as np
        forte = self._senoide(amp=0.1)
        env = np.exp(-np.linspace(0, 6, 900)).astype(np.float32)
        forte[2400:3300] += env * 0.95
        pico_transiente, _ = qc.pop_score(forte)

        estalo = self._senoide(amp=0.5)
        estalo[2400:] += 0.05
        pico_estalo, largura_estalo = qc.pop_score(estalo)

        assert pico_transiente > pico_estalo          # o legítimo é MAIS alto
        assert qc.is_pop(pico_estalo, largura_estalo)  # e mesmo assim só o estalo acusa

    def test_estalo_inaudivel_nao_conta(self):
        import numpy as np
        y = self._senoide(amp=0.5)
        y[2400:] += 0.0005                   # degrau ~-66 dBFS
        peak, width = qc.pop_score(y)
        assert not qc.is_pop(peak, width)

    def test_silencio_absoluto(self):
        import numpy as np
        peak, width = qc.pop_score(np.zeros(4800, dtype=np.float32))
        assert peak == -120.0 and width == 0
        assert not qc.is_pop(peak, width)

    def test_janela_curta_demais(self):
        import numpy as np
        assert qc.pop_score(np.zeros(2, dtype=np.float32)) == (-120.0, 0)
        assert qc.pop_score(None) == (-120.0, 0)

    def test_limiares_configuraveis(self):
        # o mesmo salto passa ou não conforme o piso escolhido
        assert qc.is_pop(-30.0, 3, floor_db=-45.0)
        assert not qc.is_pop(-30.0, 3, floor_db=-20.0)
        assert not qc.is_pop(-10.0, 20, max_width=8)
        assert qc.is_pop(-10.0, 20, max_width=30)

    def test_largura_zero_nunca_e_estalo(self):
        assert not qc.is_pop(-5.0, 0)
