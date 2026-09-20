"""Punch, speed e handles de transição — a matemática do render."""
import pytest
from conftest import load

render = load("render")


class TestPunch:
    def test_sem_punch_devolve_vazio(self):
        assert render.build_punch_filter(None, 5.0) == ""
        assert render.build_punch_filter(1.0, 5.0) == ""

    def test_zoom_fixo(self):
        f = render.build_punch_filter(1.2, 5.0, src_size=(1920, 1080))
        assert f.startswith("crop=")
        assert "1.200000" in f
        assert "zoompan" not in f             # estático não precisa de zoompan

    def test_rampa_usa_zoompan_com_tamanho_explicito(self):
        # crop não serve para rampa: dimensão de saída é fixada na configuração
        f = render.build_punch_filter({"from": 1.0, "to": 1.15}, 4.0,
                                      src_size=(1920, 1080), fps=30)
        assert f.startswith("zoompan=")
        assert "s=1920x1080" in f
        assert "d=1" in f and "fps=30" in f
        assert "on/" in f                       # progresso por frame de saída

    def test_rampa_sem_tamanho_cai_para_zoom_medio(self):
        f = render.build_punch_filter({"from": 1.0, "to": 1.2}, 4.0, src_size=None)
        assert f.startswith("crop=")
        assert "1.100000" in f                  # média de 1.0 e 1.2

    def test_rampa_vai_de_um_zoom_ao_outro(self):
        f = render.build_punch_filter({"from": 1.0, "to": 1.15}, 2.0,
                                      src_size=(1920, 1080), fps=30)
        assert "1.000000+(0.150000)" in f

    def test_nenhuma_expressao_contem_virgula(self):
        # vírgula em -vf separa filtros: uma vírgula aqui quebra o grafo em silêncio
        for punch in (1.2, {"from": 1.0, "to": 1.3}, {"zoom": 1.1, "x": 0.3, "y": 0.7}):
            assert "," not in render.build_punch_filter(punch, 3.0, src_size=(1920, 1080))

    def test_parse_punch_normaliza_as_formas(self):
        assert render.parse_punch(None) is None
        assert render.parse_punch(1.0) is None           # zoom 1.0 é nada
        assert render.parse_punch(1.2) == (1.2, 1.2, 0.5, 0.5)
        assert render.parse_punch({"from": 1.0, "to": 1.1}) == (1.0, 1.1, 0.5, 0.5)
        assert render.parse_punch({"zoom": 1.3, "x": 0.2, "y": 0.8}) == (1.3, 1.3, 0.2, 0.8)

    def test_foco_fora_do_centro(self):
        f = render.build_punch_filter({"zoom": 1.2, "x": 0.25, "y": 0.75}, 3.0,
                                      src_size=(1920, 1080))
        assert "0.2500" in f and "0.7500" in f

    def test_dimensoes_sempre_pares(self):
        # yuv420p exige largura e altura pares; floor(x/2)*2 garante isso
        f = render.build_punch_filter(1.33, 3.0, src_size=(1920, 1080))
        assert f.count("floor(") == 2 and f.count("/2)*2") == 2

    def test_zoom_invalido_levanta(self):
        with pytest.raises(ValueError):
            render.build_punch_filter({"zoom": 0}, 3.0, src_size=(1920, 1080))


class TestAtempo:
    def test_velocidade_normal_nao_filtra(self):
        assert render.build_atempo_chain(1.0) == ""

    def test_dentro_da_faixa_usa_uma_instancia(self):
        assert render.build_atempo_chain(1.5) == "atempo=1.500000"

    def test_acima_de_2x_encadeia(self):
        chain = render.build_atempo_chain(4.0)
        assert chain.count("atempo") == 2
        assert chain == "atempo=2.0,atempo=2.000000"

    def test_abaixo_de_meio_encadeia(self):
        chain = render.build_atempo_chain(0.25)
        assert chain.count("atempo") == 2

    def test_produto_dos_fatores_bate_com_a_velocidade(self):
        for speed in (0.25, 0.5, 1.5, 2.0, 3.0, 4.0, 8.0):
            chain = render.build_atempo_chain(speed)
            if not chain:
                continue
            produto = 1.0
            for part in chain.split(","):
                produto *= float(part.split("=")[1])
            assert produto == pytest.approx(speed, rel=1e-4)


class TestHandlesDeTransicao:
    def test_sem_transicao_sem_handle(self):
        assert render.transition_handles({"ranges": []}) == {}

    def test_transicao_pede_metade_de_cada_lado(self):
        edl = {"transitions": [{"after": 0, "duration": 0.4}]}
        h = render.transition_handles(edl)
        assert h[0] == (0.0, 0.2)   # cauda no segmento 0
        assert h[1] == (0.2, 0.0)   # cabeça no segmento 1

    def test_segmento_entre_duas_transicoes_pede_dos_dois_lados(self):
        edl = {"transitions": [{"after": 0, "duration": 0.4},
                               {"after": 1, "duration": 0.6}]}
        h = render.transition_handles(edl)
        assert h[1] == (0.2, 0.3)

    def test_timeline_visivel_nao_muda(self):
        """O ponto dos handles: a + b entra, a + b sai (Regra Dura 13)."""
        d = 0.4
        a, b = 3.0, 5.0
        dur_a = a + d / 2          # segmento A com cauda extra
        dur_b = d / 2 + b          # segmento B com cabeça extra
        saida = dur_a + dur_b - d  # xfade sobrepõe d segundos
        assert saida == pytest.approx(a + b)

    def test_xfade_aceita_os_tipos_documentados(self):
        for t in ("fade", "dissolve", "wipeleft", "circleopen", "pixelize", "zoomin"):
            assert t in render.XFADE_TYPES


class TestComandoDeExtracao:
    """O comando de extração é onde erros de -ss/-t viram corte errado em silêncio."""

    def _capture(self, tmp_path, **kwargs):
        import subprocess
        from unittest.mock import patch
        captured = {}

        def fake_run(cmd, *a, **kw):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(render.subprocess, "run", side_effect=fake_run), \
             patch.object(render, "is_hdr_source", return_value=False), \
             patch.object(render, "is_portrait_source", return_value=False), \
             patch.object(render, "probe_source_fps", return_value="30/1"), \
             patch.object(render, "probe_source_size", return_value=(1920, 1080)):
            render.extract_segment(
                tmp_path / "src.mp4", kwargs.pop("start", 10.0),
                kwargs.pop("duration", 4.0), "", tmp_path / "out.mp4",
                rate="30/1", **kwargs)
        return captured["cmd"]

    def _opt_before_input(self, cmd, flag):
        i_idx = cmd.index("-i")
        return [cmd[j + 1] for j, c in enumerate(cmd) if c == flag and j < i_idx]

    def _opt_after_input(self, cmd, flag):
        i_idx = cmd.index("-i")
        return [cmd[j + 1] for j, c in enumerate(cmd) if c == flag and j > i_idx]

    def test_ss_e_t_limitam_a_entrada(self, tmp_path):
        cmd = self._capture(tmp_path)
        assert self._opt_before_input(cmd, "-ss") == ["10.000"]
        assert self._opt_before_input(cmd, "-t") == ["4.000"]

    def test_saida_sem_speed_tem_a_duracao_da_fonte(self, tmp_path):
        cmd = self._capture(tmp_path)
        assert self._opt_after_input(cmd, "-t") == ["4.000"]

    def test_speed_encurta_so_a_saida(self, tmp_path):
        """A entrada continua lendo 4s de fonte; a saída sai com 4/2 = 2s."""
        cmd = self._capture(tmp_path, speed=2.0)
        assert self._opt_before_input(cmd, "-t") == ["4.000"]
        assert self._opt_after_input(cmd, "-t") == ["2.000"]

    def test_speed_aplica_setpts_e_atempo(self, tmp_path):
        cmd = self._capture(tmp_path, speed=1.5)
        vf = cmd[cmd.index("-vf") + 1]
        af = cmd[cmd.index("-af") + 1]
        assert "setpts=PTS/1.500000" in vf
        assert "atempo=1.500000" in af

    def test_fade_ancorado_na_duracao_de_saida(self, tmp_path):
        # a 2x, 4s de fonte viram 2s de saída: o fade-out fica em 2 - 0.03
        cmd = self._capture(tmp_path, speed=2.0)
        af = cmd[cmd.index("-af") + 1]
        assert "afade=t=out:st=1.970" in af

    def test_fades_de_30ms_sempre_presentes(self, tmp_path):
        # Regra Dura 3
        af = self._capture(tmp_path)[self._capture(tmp_path).index("-af") + 1]
        assert "afade=t=in:st=0:d=0.03" in af
        assert ":d=0.03" in af

    def test_punch_entra_antes_do_scale(self, tmp_path):
        cmd = self._capture(tmp_path, punch=1.2)
        vf = cmd[cmd.index("-vf") + 1]
        assert vf.index("crop=") < vf.index("scale=")


class TestGeometriaDeSaida:
    """Segmento de dimensão divergente quebra o concat sem acusar erro."""

    def _edl(self, tmp_path, fontes):
        return {
            "sources": {nome: str(tmp_path / f"{nome}.mp4") for nome in fontes},
            "ranges": [{"source": nome, "start": 0, "end": 1} for nome in fontes],
        }

    def _resolve(self, tmp_path, fontes, orientacoes, explicit=None, draft=False):
        from unittest.mock import patch
        mapa = dict(zip(fontes, orientacoes))

        def fake_portrait(path):
            from pathlib import Path as P
            return mapa[P(path).stem] == "portrait"

        with patch.object(render, "is_portrait_source", side_effect=fake_portrait):
            return render.resolve_output_size(
                self._edl(tmp_path, fontes), tmp_path, explicit, draft=draft)

    def test_size_explicito_manda(self, tmp_path):
        assert self._resolve(tmp_path, ["A"], ["landscape"], "1080x1920") == (1080, 1920)

    def test_size_aceita_x_unicode(self, tmp_path):
        assert self._resolve(tmp_path, ["A"], ["landscape"], "1080×1920") == (1080, 1920)

    def test_size_impar_e_recusado(self, tmp_path):
        # yuv420p faz subamostragem 2x2: dimensão ímpar não codifica
        with pytest.raises(SystemExit):
            self._resolve(tmp_path, ["A"], ["landscape"], "1081x1920")

    def test_size_malformado_e_recusado(self, tmp_path):
        with pytest.raises(SystemExit):
            self._resolve(tmp_path, ["A"], ["landscape"], "vertical")

    def test_herda_orientacao_da_primeira_fonte(self, tmp_path):
        assert self._resolve(tmp_path, ["A"], ["landscape"]) == (1920, 1080)
        assert self._resolve(tmp_path, ["A"], ["portrait"]) == (1080, 1920)

    def test_draft_usa_resolucao_menor(self, tmp_path):
        assert self._resolve(tmp_path, ["A"], ["landscape"], draft=True) == (1280, 720)

    def test_orientacoes_misturadas_avisam(self, tmp_path, capsys):
        size = self._resolve(tmp_path, ["A", "B"], ["landscape", "portrait"])
        assert size == (1920, 1080)          # a primeira fonte decide
        saida = capsys.readouterr().out
        assert "mistura" in saida and "--size" in saida

    def test_orientacao_unica_nao_avisa(self, tmp_path, capsys):
        self._resolve(tmp_path, ["A", "B"], ["landscape", "landscape"])
        assert "mistura" not in capsys.readouterr().out

    def test_edl_vazio_tem_padrao(self, tmp_path):
        assert render.resolve_output_size({"ranges": []}, tmp_path, None) == (1920, 1080)


class TestFiltroDeGeometria:
    def _vf(self, tmp_path, **kwargs):
        import subprocess
        from unittest.mock import patch
        cap = {}

        def fake_run(cmd, *a, **kw):
            cap["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(render.subprocess, "run", side_effect=fake_run), \
             patch.object(render, "is_hdr_source", return_value=False), \
             patch.object(render, "is_portrait_source", return_value=False), \
             patch.object(render, "probe_source_fps", return_value="30/1"), \
             patch.object(render, "probe_source_size", return_value=(1920, 1080)):
            render.extract_segment(tmp_path / "s.mp4", 0.0, 2.0, "", tmp_path / "o.mp4",
                                   rate="30/1", **kwargs)
        return cap["cmd"][cap["cmd"].index("-vf") + 1]

    def test_toda_fonte_cai_na_mesma_geometria(self, tmp_path):
        vf = self._vf(tmp_path, out_size=(1080, 1920))
        assert "scale=1080:1920:force_original_aspect_ratio=decrease" in vf
        assert "pad=1080:1920" in vf

    def test_pad_centraliza(self, tmp_path):
        vf = self._vf(tmp_path, out_size=(1920, 1080))
        assert "(ow-iw)/2:(oh-ih)/2" in vf

    def test_setsar_normaliza_o_pixel_aspect(self, tmp_path):
        # o crop do punch deixa SAR quebrado (7713:7712) e o concat fica heterogêneo
        vf = self._vf(tmp_path, out_size=(1920, 1080), punch=1.2)
        assert "setsar=1" in vf

    def test_ordem_punch_escala_pad(self, tmp_path):
        vf = self._vf(tmp_path, out_size=(1920, 1080), punch=1.15)
        assert vf.index("crop=") < vf.index("scale=") < vf.index("pad=")
