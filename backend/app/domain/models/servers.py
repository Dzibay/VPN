import re
import uuid as uuid_lib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.servers.host_validation import (
    is_domain_host,
    normalize_grpc_service_name,
    normalize_ws_path,
    normalize_xhttp_path,
)

ProxyKind = Literal[
    "vless",
    "vless_grpc",
    "vless_ws",
    "vless_xhttp",
    "vless_vk_cdn_xhttp",
    "hysteria2",
]


class ServersCountResponse(BaseModel):
    servers_count: int = Field(ge=0, description="Число записей в таблице servers")


class ServerCreate(BaseModel):
    name: str | None = Field(
        default=None,
        max_length=256,
        description="Подпись в админке (необязательно)",
    )
    host: str = Field(
        min_length=1,
        max_length=512,
        description="IP или доменное имя узла",
    )
    ssh_user: str = Field(
        default="root",
        max_length=64,
        description="Пользователь SSH для провижининга и управления узлом",
    )
    port: int = Field(
        default=443,
        ge=1,
        le=65535,
        description="Порт inbound (VLESS REALITY)",
    )
    country: str = Field(
        min_length=1,
        max_length=128,
        description="Страна (код ISO, название или метка для клиента)",
    )
    load_percent: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Оценка загрузки 0–100 (для сортировки/отбора при выдаче подписки)",
    )
    is_active: bool = Field(default=True, description="Учитывать узел при выдаче подписки")
    whitelist: bool = Field(
        default=False,
        description="Узел для белого списка (выдача только отмеченным пользователям — при поддержке в приложении)",
    )
    include_in_auto: bool = Field(
        default=True,
        description="Включать узел в группы Auto (рекомендуемый / белые списки) с балансировкой по пингу",
    )
    is_hidden: bool = Field(
        default=False,
        description="Скрытый узел: не выдаётся в подписке; в админке скрыт из таблицы, пока не включён показ",
    )
    proxy_kind: ProxyKind = Field(
        default="vless",
        description=(
            "Тип прокси: vless (REALITY), vless_grpc (gRPC+TLS), vless_ws (WS+TLS), "
            "vless_xhttp (XHTTP+TLS), vless_vk_cdn_xhttp (VK Cloud CDN + XHTTP) или hysteria2"
        ),
    )
    vless_uuid: str | None = Field(
        default=None,
        max_length=64,
        description="UUID клиента VLESS; пусто — сгенерировать",
    )
    reality_short_id: str | None = Field(
        default=None,
        max_length=32,
        description="shortId REALITY (hex); пусто — сгенерировать",
    )
    reality_dest: str | None = Field(
        default=None,
        max_length=256,
        description="dest REALITY host:port (маскировка), по умолчанию Amazon",
    )
    reality_server_names: str | None = Field(
        default=None,
        max_length=512,
        description="serverNames через запятую; по умолчанию домены Amazon",
    )
    reality_fingerprint: str | None = Field(
        default=None,
        max_length=64,
        description="uTLS fingerprint, по умолчанию chrome",
    )
    reality_spider_x: str | None = Field(
        default=None,
        max_length=256,
        description="REALITY spiderX — путь к ресурсу на dest (напр. / или /favicon.ico); пусто — /",
    )
    vless_flow: str | None = Field(
        default=None,
        max_length=64,
        description="flow для tcp+xtls, по умолчанию xtls-rprx-vision",
    )
    grpc_service_name: str | None = Field(
        default=None,
        max_length=64,
        description="Имя gRPC-сервиса (VLESS gRPC+TLS); по умолчанию grpc",
    )
    tls_sni: str | None = Field(
        default=None,
        max_length=256,
        description="SNI для TLS (gRPC/WS); по умолчанию host",
    )
    ws_path: str | None = Field(
        default=None,
        max_length=256,
        description="Путь WebSocket (VLESS WS+TLS); по умолчанию /vless",
    )
    origin_domain: str | None = Field(
        default=None,
        max_length=253,
        description="Origin-домен VPS для VK Cloud CDN (A-запись на сервер)",
    )
    cdn_domain: str | None = Field(
        default=None,
        max_length=253,
        description="Клиентский CDN-домен VK Cloud (CNAME на CDN-ресурс)",
    )
    xhttp_path: str | None = Field(
        default=None,
        max_length=256,
        description="XHTTP path для VK Cloud CDN; по умолчанию /uploadfiles/",
    )
    prometheus_instance: str | None = Field(
        default=None,
        max_length=256,
        description=(
            "Опционально: label instance в Prometheus; пусто — используется host и порт из "
            "PROVISION_NODE_EXPORTER_PORT на API"
        ),
    )
    network_cap_mbps: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        description="Тарифный потолок канала (Мбит/с) для шкалы графика сети; пусто — только NIC из метрик",
    )
    is_cascade_ru_entry: bool = Field(
        default=False,
        description="Вход в каскаде (РФ): к нему дальше подключается внешний exit-сервер",
    )
    cascade_next_server_id: int | None = Field(
        default=None,
        description="ID внешнего exit-сервера; только вместе с is_cascade_ru_entry (подготовка к каскаду Xray)",
    )
    google_routing_mode: Literal["exit", "entry"] = Field(
        default="exit",
        description=(
            "Маршрутизация Google на каскадном входе: exit — Gemini и geoip:google через exit; "
            "entry — YouTube/Google через Cloudflare WARP на входе, Gemini — direct"
        ),
    )

    @field_validator("google_routing_mode", mode="before")
    @classmethod
    def normalize_google_routing_mode_create(cls, v: Any) -> str:
        s = (str(v).strip().lower() if v is not None else "") or "exit"
        if s not in ("exit", "entry"):
            raise ValueError("google_routing_mode: exit или entry")
        return s

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("host", mode="before")
    @classmethod
    def normalize_host(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("host: не может быть пустым")
        return s

    @field_validator("ssh_user", mode="before")
    @classmethod
    def normalize_ssh_user(cls, v: Any) -> str:
        if v is None:
            return "root"
        s = str(v).strip()
        if not s:
            return "root"
        if "@" in s or "/" in s or " " in s:
            raise ValueError("ssh_user: невалидное имя пользователя")
        return s

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("country: укажите страну")
        return s

    @field_validator("vless_uuid", mode="before")
    @classmethod
    def normalize_vless_uuid(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        try:
            uuid_lib.UUID(s)
        except ValueError as e:
            raise ValueError("vless_uuid: невалидный UUID") from e
        return s

    @field_validator("reality_short_id", mode="before")
    @classmethod
    def normalize_short_id(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip().lower()
        if not s:
            return None
        if not re.fullmatch(r"[0-9a-f]{2,16}", s):
            raise ValueError("reality_short_id: только hex, 2–16 символов")
        return s

    @field_validator("reality_dest", "reality_server_names", mode="before")
    @classmethod
    def strip_opt(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("reality_fingerprint", "vless_flow", mode="before")
    @classmethod
    def strip_small(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("reality_spider_x", mode="before")
    @classmethod
    def normalize_reality_spider_x_create(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        from app.domain.servers.reality_defaults import normalize_reality_spider_x

        return normalize_reality_spider_x(s)

    @field_validator("grpc_service_name", mode="before")
    @classmethod
    def normalize_grpc_service_name_create(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return normalize_grpc_service_name(s)

    @field_validator("ws_path", mode="before")
    @classmethod
    def normalize_ws_path_create(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return normalize_ws_path(s)

    @field_validator("origin_domain", "cdn_domain", mode="before")
    @classmethod
    def normalize_cdn_domain_create(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip().rstrip(".").lower()
        return s if s else None

    @field_validator("xhttp_path", mode="before")
    @classmethod
    def normalize_xhttp_path_create(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return normalize_xhttp_path(s)

    @field_validator("tls_sni", mode="before")
    @classmethod
    def normalize_tls_sni_create(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip().rstrip(".")
        return s if s else None

    @model_validator(mode="after")
    def validate_tls_transport_create(self) -> "ServerCreate":
        if self.proxy_kind == "vless_vk_cdn_xhttp":
            origin = (self.origin_domain or "").strip()
            cdn = (self.cdn_domain or "").strip()
            if not origin or not is_domain_host(origin):
                raise ValueError("origin_domain: укажите домен origin с A-записью на VPS")
            if not cdn or not is_domain_host(cdn):
                raise ValueError("cdn_domain: укажите CDN-домен VK Cloud")
            return self
        if self.proxy_kind not in ("vless_grpc", "vless_ws", "vless_xhttp"):
            return self
        if not is_domain_host(self.host):
            raise ValueError(
                "host: для VLESS gRPC/WebSocket/XHTTP+TLS нужен домен (A-запись на узел)",
            )
        sni = (self.tls_sni or self.host).strip()
        if not is_domain_host(sni):
            raise ValueError("tls_sni: укажите валидный домен для TLS")
        return self

    @field_validator("prometheus_instance", mode="before")
    @classmethod
    def normalize_prom_instance(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("network_cap_mbps", mode="before")
    @classmethod
    def normalize_network_cap_create(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("network_cap_mbps: ожидается целое число") from None
        if n < 1 or n > 1_000_000:
            raise ValueError("network_cap_mbps: 1…1000000")
        return n

    @field_validator("cascade_next_server_id", mode="before")
    @classmethod
    def normalize_cascade_next_create(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("cascade_next_server_id: ожидается id сервера") from None
        if n < 1:
            raise ValueError("cascade_next_server_id: невалидный id")
        return n


class ServerUpdate(BaseModel):
    """Частичное обновление (админка: правка нагрузки и метаданных)."""

    name: str | None = Field(default=None, max_length=256)
    country: str | None = Field(default=None, max_length=128)
    load_percent: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    whitelist: bool | None = Field(
        default=None,
        description="Флаг белого списка для узла",
    )
    include_in_auto: bool | None = Field(
        default=None,
        description="Участие в группах Auto (балансировка по пингу)",
    )
    is_hidden: bool | None = Field(
        default=None,
        description="Скрытый узел (не в подписке; в админке по умолчанию не в таблице)",
    )
    proxy_kind: ProxyKind | None = Field(
        default=None,
        description="Тип прокси на узле",
    )
    reality_dest: str | None = Field(default=None, max_length=256)
    reality_server_names: str | None = Field(default=None, max_length=512)
    reality_fingerprint: str | None = Field(default=None, max_length=64)
    reality_spider_x: str | None = Field(
        default=None,
        max_length=256,
        description="REALITY spiderX; пустая строка сбрасывает к / на сервере при следующем провижининге",
    )
    vless_flow: str | None = Field(default=None, max_length=64)
    grpc_service_name: str | None = Field(default=None, max_length=64)
    tls_sni: str | None = Field(default=None, max_length=256)
    ws_path: str | None = Field(default=None, max_length=256)
    origin_domain: str | None = Field(default=None, max_length=253)
    cdn_domain: str | None = Field(default=None, max_length=253)
    xhttp_path: str | None = Field(default=None, max_length=256)
    reality_short_id: str | None = Field(default=None, max_length=32)
    reality_private_key: str | None = Field(
        default=None,
        max_length=512,
        description="Приватный ключ REALITY (опционально); публичный пересчитается при установке",
    )
    prometheus_instance: str | None = Field(
        default=None,
        max_length=256,
        description="Override label instance; null/пусто — по умолчанию host:PROVISION_NODE_EXPORTER_PORT",
    )
    network_cap_mbps: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        description="Тарифный потолок (Мбит/с); null — сбросить",
    )
    is_cascade_ru_entry: bool | None = Field(
        default=None,
        description="Вход (РФ) в каскаде; false — сбросить каскад (и cascade_next)",
    )
    cascade_next_server_id: int | None = Field(
        default=None,
        description="Id внешнего exit; null — отвязать. Только у входа is_cascade_ru_entry",
    )
    google_routing_mode: Literal["exit", "entry"] | None = Field(
        default=None,
        description="Маршрутизация Google/YouTube на каскадном входе (exit | entry)",
    )

    @field_validator("google_routing_mode", mode="before")
    @classmethod
    def normalize_google_routing_mode_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip().lower()
        if not s:
            return None
        if s not in ("exit", "entry"):
            raise ValueError("google_routing_mode: exit или entry")
        return s

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            raise ValueError("country: не может быть пустым")
        return s

    @field_validator(
        "reality_dest",
        "reality_server_names",
        "reality_fingerprint",
        "vless_flow",
        mode="before",
    )
    @classmethod
    def strip_optional(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("reality_spider_x", mode="before")
    @classmethod
    def normalize_reality_spider_x_update(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return "/"
        from app.domain.servers.reality_defaults import normalize_reality_spider_x

        return normalize_reality_spider_x(s)

    @field_validator("grpc_service_name", mode="before")
    @classmethod
    def normalize_grpc_service_name_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return normalize_grpc_service_name(s)

    @field_validator("tls_sni", mode="before")
    @classmethod
    def normalize_tls_sni_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip().rstrip(".")
        return s if s else None

    @field_validator("ws_path", mode="before")
    @classmethod
    def normalize_ws_path_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return normalize_ws_path(s)

    @field_validator("origin_domain", "cdn_domain", mode="before")
    @classmethod
    def normalize_cdn_domain_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip().rstrip(".").lower()
        return s if s else None

    @field_validator("xhttp_path", mode="before")
    @classmethod
    def normalize_xhttp_path_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return normalize_xhttp_path(s)

    @field_validator("reality_short_id", mode="before")
    @classmethod
    def normalize_short_id_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip().lower()
        if not s:
            return None
        if not re.fullmatch(r"[0-9a-f]{2,16}", s):
            raise ValueError("reality_short_id: только hex, 2–16 символов")
        return s

    @field_validator("reality_private_key", mode="before")
    @classmethod
    def normalize_priv(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("prometheus_instance", mode="before")
    @classmethod
    def normalize_prom_patch(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("network_cap_mbps", mode="before")
    @classmethod
    def normalize_network_cap_patch(cls, v: object) -> int | None:
        if v is None:
            return None
        if v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("network_cap_mbps: ожидается целое число") from None
        if n < 1 or n > 1_000_000:
            raise ValueError("network_cap_mbps: 1…1000000")
        return n

    @field_validator("cascade_next_server_id", mode="before")
    @classmethod
    def normalize_cascade_next_patch(cls, v: object) -> int | None:
        if v is None:
            return None
        if v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("cascade_next_server_id: ожидается id сервера") from None
        if n < 1:
            raise ValueError("cascade_next_server_id: невалидный id")
        return n


class ServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    host: str
    ssh_user: str = Field(
        default="root",
        description="Пользователь SSH для провижининга и управления узлом",
    )
    port: int
    country: str
    load_percent: int
    is_active: bool
    whitelist: bool = Field(
        default=False,
        description="Сервер помечен для выдачи в белом списке",
    )
    include_in_auto: bool = Field(
        default=True,
        description="Участвует в группах Auto (рекомендуемый / белые списки), не только отдельной строкой",
    )
    is_hidden: bool = Field(
        default=False,
        description="Скрытый узел: не в подписке; в админке по умолчанию не показывается в таблице",
    )
    provision_ready: bool = Field(description="ПО на узле установлено (воркер завершил задачу)")
    provision_status: str = Field(
        description="idle | queued | running | success | failed",
    )
    provision_error: str | None = Field(description="Текст ошибки при failed")
    provision_job_id: str | None = Field(description="ID последней задачи RQ")
    provision_step: str | None = Field(
        default=None,
        description="Текущий человекочитаемый этап установки ПО",
    )
    provision_progress: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Прогресс установки ПО, 0–100",
    )
    provision_detail: str | None = Field(
        default=None,
        description="Краткая деталь текущего этапа или понятная причина ошибки",
    )
    proxy_kind: ProxyKind = Field(
        default="vless",
        description="Тип прокси на узле",
    )
    grpc_service_name: str = Field(
        default="grpc",
        description="Имя gRPC-сервиса (VLESS gRPC+TLS)",
    )
    tls_sni: str | None = Field(
        default=None,
        description="SNI для TLS; null — host",
    )
    ws_path: str = Field(
        default="/vless",
        description="Путь WebSocket (VLESS WS+TLS)",
    )
    origin_domain: str | None = Field(
        default=None,
        description="Origin-домен VPS для VK Cloud CDN",
    )
    cdn_domain: str | None = Field(
        default=None,
        description="Клиентский CDN-домен VK Cloud",
    )
    xhttp_path: str = Field(
        default="/uploadfiles/",
        description="XHTTP path (plain XHTTP или VK Cloud CDN)",
    )
    vless_uuid: str
    reality_private_key: str | None
    reality_public_key: str | None
    reality_short_id: str
    reality_dest: str
    reality_server_names: str
    reality_fingerprint: str
    reality_spider_x: str = Field(
        default="/",
        description="REALITY spiderX (путь к dest для имитации запроса к сайту)",
    )
    vless_flow: str
    prometheus_instance: str | None = Field(
        default=None,
        description="Override instance для PromQL; null — host + порт из настроек API",
    )
    network_cap_mbps: int | None = Field(
        default=None,
        description="Тарифный потолок канала (Мбит/с) для графика сети",
    )
    is_cascade_ru_entry: bool = Field(
        default=False,
        description="Сервер — вход (РФ) в каскаде, дальше трафик на cascade_next",
    )
    cascade_next_server_id: int | None = Field(
        default=None,
        description="Id внешнего exit-сервера; не null — пара каскада настроена в БД",
    )
    cascade_egress_client_uuid: str | None = Field(
        default=None,
        description="UUID VLESS: этот (РФ) вход → на внешний exit; должен быть в inbound exit",
    )
    google_routing_mode: Literal["exit", "entry"] = Field(
        default="exit",
        description="exit: Google/Gemini через exit; entry: YouTube через WARP на входе",
    )


class ServerLoadSyncItemRead(BaseModel):
    server_id: int
    host: str
    ok: bool
    load_percent: int | None = None
    detail: str = ""


class ServerLoadSyncResultRead(BaseModel):
    """Ответ POST /servers/sync-load-from-prometheus."""

    hours: int
    items: list[ServerLoadSyncItemRead]
    updated: int = Field(ge=0, description="Число серверов, где load_percent обновлён")
    failed: int = Field(ge=0, description="Число серверов с ошибкой или без данных")


class XrayClientsSyncResultRead(BaseModel):
    """Ответ POST /servers/sync-xray-clients — постановка задачи RQ."""

    job_id: str = Field(description="ID задачи воркера (синхронизация inbound по всем готовым узлам)")


class XrayClientsSyncOneResultRead(BaseModel):
    """Ответ POST /servers/{id}/sync-xray-clients."""

    server_id: int
    job_id: str = Field(description="ID задачи RQ на один узел")


class HealthCheckItemRead(BaseModel):
    """Одна подпункт в комплексной проверке /servers/{id}/ping."""

    id: str = Field(description="стабильный идентификатор, напр. tcp_vless_inbound")
    label: str
    ok: bool
    detail: str = Field(
        default="",
        description="Пояснение: «OK» или причина сбоя / что не так в БД",
    )
    severity: Literal["critical", "warning", "info"] = Field(
        default="critical",
        description="critical — блокирует overall_ok; warning/info — важность ниже",
    )
    latency_ms: float | None = Field(
        default=None,
        description="для TCP-проверок, мс",
    )


class ServerPingRead(BaseModel):
    """
    GET /servers/{id}/ping — с хоста API: TCP к узлу + сверка с БД, каскад, node_exporter.
    `reachable` — только TCP к порту Xray; `overall_ok` — совокупная оценка.
    """

    server_id: int
    host: str
    port: int
    reachable: bool
    latency_ms: float | None = Field(
        default=None,
        description="время до успешного TCP connect к host:port (VLESS/REALITY), мс",
    )
    detail: str = Field(
        default="",
        description="кратко: как при одной проверке; для совместимости повторяет начало summary",
    )
    check: str = Field(
        default="health_multi",
        description="Сейчас: health_multi (TCP + БД + каскад + метрики).",
    )
    overall_ok: bool = Field(
        default=False,
        description="true, если критичные проверки пройдены (см. checks[].severity).",
    )
    summary: str = Field(
        default="",
        description="2–4 предложения на русском: итог и что сделать при ошибке",
    )
    checks: list[HealthCheckItemRead] = Field(
        default_factory=list,
        description="подробные пункты в порядке важности",
    )


class ServerReachabilitySampleRead(BaseModel):
    """Один снимок фонового TCP-опроса (источник — Redis, планировщик scheduler)."""

    model_config = ConfigDict(extra="ignore")

    ts: float = Field(description="Unix time записи снимка")
    vpn_ok: bool = Field(default=False, description="TCP к inbound VPN-порту узла")
    vpn_ms: float | None = None
    vpn_err: str = ""
    ne_ok: bool | None = Field(default=None, description="TCP к node_exporter, если пробовалось")
    ne_ms: float | None = None
    ne_err: str = ""
    exit_ok: bool | None = Field(default=None, description="TCP к exit каскада, если есть")
    exit_ms: float | None = None
    exit_err: str = ""


class ServerReachabilityHistoryRead(BaseModel):
    """GET /servers/{id}/reachability-history — скользящее окно из Redis."""

    server_id: int
    samples: list[ServerReachabilitySampleRead] = Field(default_factory=list)


class ServerReachabilitySummaryRowRead(BaseModel):
    """Одна строка сводки GET /servers/reachability-summary."""

    server_id: int
    name: str | None = None
    host: str
    port: int
    is_active: bool
    provision_ready: bool
    samples_total: int = Field(ge=0, description="Число снимков в окне")
    vpn_ok_count: int = Field(ge=0)
    vpn_ok_percent: float = Field(ge=0, le=100, description="Доля успешных TCP к VPN-порту")
    last_probe_ts: float | None = Field(default=None, description="Unix time последнего снимка")
    last_vpn_ok: bool | None = Field(default=None)
    avg_vpn_latency_ms: float | None = None
    ne_ok_percent: float | None = Field(
        default=None,
        description="Среди снимков с ne_ok — процент успешных TCP к node_exporter",
    )
    exit_ok_percent: float | None = Field(
        default=None,
        description="Среди снимков с exit_ok — процент успешных TCP к exit каскада",
    )


class ServersReachabilitySummaryRead(BaseModel):
    """Сводка доступности по всем серверам из Redis + метаданные из БД."""

    hours_window: float
    probe_interval_seconds_hint: int = Field(
        description="Интервал цикла фонового опроса из настроек планировщика (сек)",
    )
    servers: list[ServerReachabilitySummaryRowRead] = Field(default_factory=list)
