from scripts.recertification_gain import comparar


def test_accepted_zero_is_present_not_unknown():
    assert comparar({"precio": 0}, {"precio": None})["precio"] == "pierde"
    assert comparar({"banos": None}, {"banos": 0})["banos"] == "gana"
    assert comparar({"precio": 0}, {"precio": 0})["precio"] == "igual"


def test_changed_value_is_not_equal_or_automatically_better():
    result = comparar({"banos": 3, "provincia": "CABA"},
                      {"banos": 1, "provincia": "Buenos Aires"})
    assert result["banos"] == result["provincia"] == "cambia"
