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


class TestCadeiaLoud:
    """Atingir o alvo de loudness é questão de ataque, não de limiter.

    Medido neste repo, normalizando para I=-14:TP=-1.5 depois de cada cadeia,
    numa fala com razão pico/loudness de 17.1 dB:

        sem tratamento                  -20.5 LUFS
        clean (ataque 8ms, ratio 3)     -15.2 LUFS
        alimiter sozinho                -15.5 LUFS
        loud  (ataque 1ms, ratio 6)     -14.1 LUFS  <- no alvo
    """

    def test_existe_uma_cadeia_para_atingir_o_alvo(self):
        assert "loud" in audio_post.CHAINS

    def test_ataque_rapido_e_o_que_distingue_de_clean(self):
        import re
        def attack(chain):
            m = re.search(r"acompressor=[^,]*attack=(\d+(?:\.\d+)?)", chain)
            return float(m.group(1)) if m else None
        assert attack(audio_post.CHAINS["loud"]) < attack(audio_post.CHAINS["clean"])

    def test_ratio_maior_que_clean(self):
        import re
        def ratio(chain):
            m = re.search(r"acompressor=[^,]*ratio=(\d+(?:\.\d+)?)", chain)
            return float(m.group(1)) if m else None
        assert ratio(audio_post.CHAINS["loud"]) > ratio(audio_post.CHAINS["clean"])

    def test_mantem_o_tratamento_de_voz(self):
        # não é só compressão: continua sendo uma cadeia de voz completa
        for peca in ("highpass", "deesser", "equalizer"):
            assert peca in audio_post.CHAINS["loud"]


class TestTetoDePico:
    """O AAC faz overshoot depois da normalização.

    Medido: mirando TP=-1, o arquivo sai a -1.00 dBTP em PCM, -0.62 em AAC
    128k e +0.30 em AAC 192k — este último clipa no player. Mirar -1.5 entrega
    -1.05, que é onde se queria chegar.
    """

    def test_alvos_deixam_margem_para_o_codec(self):
        for nome, (_, tp, _) in audio_post.TARGETS.items():
            assert tp <= -1.5, f"{nome}: teto {tp} não absorve overshoot do AAC"

    def test_broadcast_e_cinema_tem_teto_ainda_mais_baixo(self):
        assert audio_post.TARGETS["broadcast"][1] <= -2.0
        assert audio_post.TARGETS["cinema"][1] <= -3.0
