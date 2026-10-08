"""Una pagina que NOMBRA a la agencia no es su web: el host tiene que ser de la agencia (mision 08-10).

Casos reales de la re-verificacion permisiva del 08-10 (revertida antes de que la cola los tomara).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verificar_webs_del_directorio import dominio_propio  # noqa: E402


def test_MUERDE_sitios_de_terceros_que_solo_nombran_a_la_agencia():
    for cid, url in (
            ("roomix:a zaccardi propiedades", "https://www.respaldar.com.ar/pre-aprobado-express-sin-cargo"),
            ("roomix:anahi gerosa cmcpsi6900", "https://www.asia.villas/property-sales/4-bedroom-house"),
            ("roomix:astorga inmobiliaria ma alejandra astorga cucicba", "https://cucicba.org.ar/matriculados"),
            ("roomix:dalessandro propiedades", "https://www.xing.com/pages/dalessandro"),
            ("roomix:casaspropiedades", "https://kasafinder.io/es/professionals/851"),
            ("roomix:fernando j vaz bienes raices cpi n 846 cmcpdsn adherido sistema coldwell banker haka",
             "https://www.coldwellbankerinternational.com/agente/fernando-vaz"),
            ("roomix:aiser propiedades", "https://www.aiser.com.ar/contenidos/2022/11/10/Editorial_3197.php"),
            ("roomix:inmobiliaria barbagallo", "https://ladefensadigital.com/nota/barbagallo")):
        assert dominio_propio(cid, url)[0] is False, url


def test_la_web_propia_pasa_tambien_con_siglas_y_subdominios_saas():
    for cid, url in (
            ("roomix:adriana dato inmobiliaria", "https://www.adrianadato.com/inmuebles?en=venta&tipo=local"),
            ("roomix:carlos negocios inmobiliarios", "https://carlosinmobiliaria.kitepropcrm.com/site/properties/1"),
            ("roomix:ieb real estate", "https://iebrealestate.com.ar/"),
            ("roomix:grupo sur y asociados", "https://gruposurneuquen.com.ar/"),
            ("roomix:gea negocios inmobiliarios", "https://geapropiedades.com/"),
            ("roomix:ar inversiones negocios inmobiliarios", "https://www.arinversiones.com.ar/p/6260672-Terreno"),
            ("roomix:gv propiedades rosario", "https://gvpropiedades.tuinmobiliaria.com.ar/"),
            ("roomix:bustamante bienes raices", "https://www.bustamantebienesraices.net/")):
        assert dominio_propio(cid, url)[0] is True, url
