"""Domain models for EconoBot database entities."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Produto:
    url: str
    ultimo_preco: Optional[float] = None
    menor_preco_semana: Optional[float] = None
    menor_preco_mes: Optional[float] = None
    menor_preco_ano: Optional[float] = None
    data_atualizacao: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Produto":
        return cls(
            url=data["url"],
            ultimo_preco=data.get("ultimo_preco"),
            menor_preco_semana=data.get("menor_preco_semana"),
            menor_preco_mes=data.get("menor_preco_mes"),
            menor_preco_ano=data.get("menor_preco_ano"),
            data_atualizacao=data.get("data_atualizacao"),
        )

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "ultimo_preco": self.ultimo_preco,
            "menor_preco_semana": self.menor_preco_semana,
            "menor_preco_mes": self.menor_preco_mes,
            "menor_preco_ano": self.menor_preco_ano,
            "data_atualizacao": self.data_atualizacao,
        }


@dataclass
class HistoricoPreco:
    id: Optional[int] = None
    produto_url: str = ""
    preco: float = 0.0
    data_hora: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "HistoricoPreco":
        return cls(
            id=data.get("id"),
            produto_url=data.get("produto_url", ""),
            preco=float(data.get("preco", 0.0)),
            data_hora=data.get("data_hora", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "produto_url": self.produto_url,
            "preco": self.preco,
            "data_hora": self.data_hora,
        }
