"""Áudio: cadeias, alvos de loudness e o grafo de mixagem com ducking."""
import pytest
from conftest import load

audio_post = load("audio_post")


class TestAlvos:
    def test_redes_sociais_em_menos_14(self):
        for rede in ("tiktok", "reels", "shorts", "youtube", "instagram"):
            assert audio_post.TARGETS[rede][0] == -14.0

    def test_broadcast_segue_ebu_r128(self):
        assert audio_post.TARGETS["broadcast"][0] == -23.0

    def test_pico_real_nunca_acima_de_menos_1(self):
        for nome, (_, tp, _) in audio_post.TARGETS.items():
            assert tp <= -1.0, nome


class TestCadeias:
    def test_none_e_vazia(self):
        assert audio_post.CHAINS["none"] == ""

    def test_toda_cadeia_de_voz_tem_highpass(self):
        # rumble abaixo de 60-100Hz não carrega informação de voz, só energia
        for nome in ("gentle", "clean", "rescue"):
            assert "highpass" in audio_post.CHAINS[nome]

    def test_rescue_e_mais_agressiva_que_clean(self):
        assert "anlmdn" in audio_post.CHAINS["rescue"]
        assert "anlmdn" not in audio_post.CHAINS["clean"]

    def test_cadeias_nao_tem_aspas_soltas(self):
        for nome, chain in audio_post.CHAINS.items():
            assert chain.count("'") % 2 == 0, nome


class TestFiltroDeVoz:
    def test_sem_nada_so_reamostra(self):
        assert audio_post.build_voice_chain(None, None, None) == "aresample=48000"

    def test_limpeza_vem_antes_do_loudnorm(self):
        chain = audio_post.build_voice_chain("clean", "tiktok", None)
        assert chain.index("highpass") < chain.index("loudnorm")

    def test_medidas_ativam_o_modo_linear(self):
        medido = {"input_i": "-20.1", "input_tp": "-3.2",
                  "input_lra": "8.1", "input_thresh": "-30.5"}
        chain = audio_post.build_voice_chain(None, "youtube", medido)
        assert "linear=true" in chain
        assert "measured_I=-20.1" in chain

    def test_sem_medidas_nao_finge_segundo_passe(self):
        chain = audio_post.build_voice_chain(None, "youtube", None)
        assert "linear=true" not in chain
        assert "measured_I" not in chain


class TestGrafoDeMusica:
    def test_ducking_usa_sidechain_com_a_voz(self):
        g = audio_post.build_music_graph(-20, True, 8.0, 1.0, 2.0, 30.0)
        assert "sidechaincompress" in g
        assert "asplit" in g          # a voz vai para a saída E para a cadeia lateral
        assert g.endswith("[aout]")

    def test_sem_ducking_e_so_amix(self):
        g = audio_post.build_music_graph(-20, False, 8.0, 1.0, 2.0, 30.0)
        assert "sidechaincompress" not in g
        assert "amix" in g

    def test_fade_out_ancorado_no_fim(self):
        g = audio_post.build_music_graph(-20, False, 8.0, 1.0, 2.0, 30.0)
        assert "afade=t=out:st=28.000" in g

    def test_audio_curto_nao_gera_fade_negativo(self):
        g = audio_post.build_music_graph(-20, False, 8.0, 1.0, 5.0, 2.0)
        assert "st=-" not in g

    def test_normalize_desligado_no_amix(self):
        # normalize=1 divide o volume pelo número de entradas e derruba a voz
        g = audio_post.build_music_graph(-20, True, 8.0, 1.0, 2.0, 30.0)
        assert "normalize=0" in g

    def test_ganho_da_musica_entra_em_db(self):
        g = audio_post.build_music_graph(-18, True, 8.0, 1.0, 2.0, 30.0)
        assert "volume=-18dB" in g
