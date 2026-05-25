# services/modbus_reader.py
# Lectura Modbus TCP de medidores Red Seal JW2020/JW2029
# vía gateway LINOVISION RS485 → Ethernet
#
# Sin dependencias externas — usa sockets Python estándar.
# Para uso en producción con múltiples medidores, considera
# la librería `pymodbus` para manejo de reconexión automática.

import json
import logging
import socket
import struct
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ESTRUCTURA DE DATOS — Objeto JSON de lectura volumétrica
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LecturaMedidor:
    """
    Representa una lectura de medidor de flujo Red Seal.
    Se serializa directamente a JSON para reportes y persistencia.
    """
    medidor_id:        str    # Identificador único del medidor (ej. "CORIOLIS-01")
    timestamp:         str    # ISO 8601 UTC (ej. "2026-04-15T14:30:00+00:00")
    flujo_instantaneo: float  # Caudal en litros/minuto (o m³/h según config)
    totalizador:       float  # Volumen acumulado en litros desde último reset
    temperatura:       float  # Temperatura del fluido en °C
    presion:           float  # Presión de operación en kPa
    unidad_flujo:      str = "L/min"
    fuente:            str = "modbus_tcp"  # "modbus_tcp" | "simulador"

    def to_json(self) -> str:
        """Serializa a JSON compacto con tipos correctos."""
        return json.dumps(asdict(self), ensure_ascii=False)

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# 2. MAPA DE REGISTROS — Red Seal JW2020 / JW2029
#    IMPORTANTE: Verificar con el manual de tu modelo específico.
#    Estos registros son representativos; el manual puede variar.
# ─────────────────────────────────────────────────────────────────────────────

# Cada variable ocupa 2 registros de 16 bits → Float32 IEEE 754 Big-Endian
REG_FLUJO_INSTANTANEO = 0x0000   # 2 registros — Float32 L/min
REG_TOTALIZADOR_LO    = 0x0010   # 2 registros — UInt32 (totalizador en pulsos)
REG_TEMPERATURA       = 0x0020   # 2 registros — Float32 °C
REG_PRESION           = 0x0030   # 2 registros — Float32 kPa

# Factor de conversión pulsos → litros (ajustar según configuración del medidor)
PULSOS_POR_LITRO = 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. CLIENTE MODBUS TCP — Sin dependencias externas
# ─────────────────────────────────────────────────────────────────────────────

class ModbusClient:
    """
    Cliente Modbus TCP mínimo que implementa la función 0x03
    (Read Holding Registers) sobre un socket TCP estándar.

    Compatible con el gateway LINOVISION RS485-to-Ethernet
    configurado en modo Modbus TCP Server.
    """

    def __init__(
        self,
        host:    str,
        port:    int   = 502,
        unit_id: int   = 1,
        timeout: float = 3.0,
    ):
        self.host    = host
        self.port    = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._tid   = 0   # Transaction ID — incrementa en cada petición

    # ── Conexión ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Abre la conexión TCP al gateway LINOVISION."""
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            logger.info("Modbus TCP conectado a %s:%d (unit_id=%d)", self.host, self.port, self.unit_id)
        except OSError as e:
            raise ConnectionError(f"No se pudo conectar al gateway {self.host}:{self.port} — {e}") from e

    def disconnect(self) -> None:
        """Cierra el socket limpiamente."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ── Trama Modbus TCP ──────────────────────────────────────────────────

    def _build_read_request(self, register: int, count: int) -> bytes:
        """
        Construye la trama Modbus TCP Application Protocol (MBAP + PDU).
        Formato: [TID(2)] [PID(2)=0] [Length(2)] [UnitID(1)] [FC(1)] [Addr(2)] [Count(2)]
        """
        self._tid = (self._tid + 1) % 0xFFFF
        pdu    = struct.pack(">BHH", 0x03, register, count)          # FC + Addr + Count
        length = 1 + len(pdu)                                         # UnitID + PDU
        mbap   = struct.pack(">HHH", self._tid, 0, length)            # TID + PID + Length
        return mbap + struct.pack(">B", self.unit_id) + pdu

    def _read_registers(self, register: int, count: int) -> bytes:
        """
        Envía petición FC03 y retorna los bytes de datos de respuesta.
        Maneja reconexión automática ante cierre de socket.
        """
        if not self._sock:
            raise ConnectionError("No conectado. Llama connect() primero.")

        request = self._build_read_request(register, count)

        try:
            self._sock.sendall(request)
            # MBAP header (6 bytes) + Unit ID (1) + FC (1) + Byte count (1) + data
            header   = self._sock.recv(9)
            if len(header) < 9:
                raise ValueError(f"Header Modbus incompleto: {header.hex()}")
            byte_count = header[8]
            data = b""
            while len(data) < byte_count:
                chunk = self._sock.recv(byte_count - len(data))
                if not chunk:
                    raise ConnectionError("Conexión cerrada durante lectura de datos.")
                data += chunk
            return data

        except (OSError, ConnectionResetError) as e:
            self.disconnect()
            raise ConnectionError(f"Conexión perdida al leer registro 0x{register:04X}: {e}") from e

    # ── Lectura de tipos ──────────────────────────────────────────────────

    def read_float32(self, register: int) -> float:
        """Lee 2 registros y los interpreta como Float32 IEEE 754 Big-Endian."""
        data = self._read_registers(register, 2)
        if len(data) < 4:
            raise ValueError(f"Datos insuficientes para Float32 en reg 0x{register:04X}: {data.hex()}")
        return struct.unpack(">f", data[:4])[0]

    def read_uint32(self, register: int) -> int:
        """Lee 2 registros y los interpreta como entero sin signo de 32 bits."""
        data = self._read_registers(register, 2)
        if len(data) < 4:
            raise ValueError(f"Datos insuficientes para UInt32 en reg 0x{register:04X}: {data.hex()}")
        return struct.unpack(">I", data[:4])[0]


# ─────────────────────────────────────────────────────────────────────────────
# 4. FUNCIÓN DE LECTURA DE ALTO NIVEL
# ─────────────────────────────────────────────────────────────────────────────

def leer_medidor(
    host:      str,
    medidor_id: str,
    unit_id:   int   = 1,
    port:      int   = 502,
    timeout:   float = 3.0,
) -> LecturaMedidor:
    """
    Lee todos los registros de un medidor Red Seal y retorna un LecturaMedidor.

    Ejemplo de uso:
        lectura = leer_medidor("192.168.1.100", "CORIOLIS-01")
        print(lectura.to_json())
    """
    with ModbusClient(host=host, port=port, unit_id=unit_id, timeout=timeout) as client:
        flujo     = round(client.read_float32(REG_FLUJO_INSTANTANEO), 4)
        pulsos    = client.read_uint32(REG_TOTALIZADOR_LO)
        total_l   = round(pulsos / PULSOS_POR_LITRO, 3)
        temp      = round(client.read_float32(REG_TEMPERATURA), 2)
        presion   = round(client.read_float32(REG_PRESION), 2)

    return LecturaMedidor(
        medidor_id        = medidor_id,
        timestamp         = datetime.now(timezone.utc).isoformat(),
        flujo_instantaneo = flujo,
        totalizador       = total_l,
        temperatura       = temp,
        presion           = presion,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. PERSISTENCIA ANTI-SALTOS EN TOTALIZADOR
# ─────────────────────────────────────────────────────────────────────────────

def guardar_lectura(lectura: LecturaMedidor, db_path: str) -> bool:
    """
    Guarda la lectura en SQLite con validación de continuidad del totalizador.

    Reglas de validación:
      - Si el totalizador DECRECE respecto al anterior → probable reset del medidor
      - Si el incremento es > 10,000 L en un ciclo    → probable error de lectura
      En ambos casos, la lectura se guarda pero marcada como `es_valida = 0`
      para auditoría sin contaminar cálculos de facturación.

    Retorna True si la lectura fue marcada como válida.
    """
    import sqlite3

    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS lecturas_modbus (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            medidor_id   TEXT    NOT NULL,
            timestamp    TEXT    NOT NULL,
            flujo        REAL    DEFAULT 0.0,
            totalizador  REAL    DEFAULT 0.0,
            temperatura  REAL    DEFAULT 0.0,
            presion      REAL    DEFAULT 0.0,
            es_valida    INTEGER DEFAULT 1,
            nota         TEXT    DEFAULT ''
        )
    """)

    # Consultar última lectura válida para detectar saltos
    prev = con.execute(
        "SELECT totalizador FROM lecturas_modbus "
        "WHERE medidor_id=? AND es_valida=1 ORDER BY id DESC LIMIT 1",
        (lectura.medidor_id,),
    ).fetchone()

    es_valida = 1
    nota      = ""

    if prev is not None:
        delta = lectura.totalizador - prev[0]
        if delta < 0:
            es_valida = 0
            nota = f"SALTO NEGATIVO: delta={delta:+.3f} L — posible reset del medidor"
            logger.warning("Salto negativo en %s: %+.3f L", lectura.medidor_id, delta)
        elif delta > 10_000:
            es_valida = 0
            nota = f"SALTO EXCESIVO: delta={delta:+.3f} L — posible error de lectura"
            logger.warning("Salto excesivo en %s: %+.3f L", lectura.medidor_id, delta)

    con.execute(
        "INSERT INTO lecturas_modbus "
        "(medidor_id, timestamp, flujo, totalizador, temperatura, presion, es_valida, nota) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            lectura.medidor_id, lectura.timestamp,
            lectura.flujo_instantaneo, lectura.totalizador,
            lectura.temperatura, lectura.presion,
            es_valida, nota,
        ),
    )
    con.commit()
    con.close()
    return es_valida == 1


def obtener_delta_periodo(
    medidor_id: str,
    desde:      str,
    hasta:      str,
    db_path:    str,
) -> float:
    """
    Calcula el volumen neto entregado en un periodo usando solo lecturas válidas.
    Útil para conciliar totalizador vs. CFDIs en controles volumétricos.

    desde / hasta : ISO 8601, ej. "2026-04-01T00:00:00+00:00"
    Retorna: float litros netos en el período
    """
    import sqlite3

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT totalizador FROM lecturas_modbus "
        "WHERE medidor_id=? AND timestamp>=? AND timestamp<=? AND es_valida=1 "
        "ORDER BY timestamp ASC",
        (medidor_id, desde, hasta),
    ).fetchall()
    con.close()

    if len(rows) < 2:
        return 0.0
    return round(rows[-1][0] - rows[0][0], 3)


# ─────────────────────────────────────────────────────────────────────────────
# 6. SIMULADOR (MOCK) — Para desarrollo sin hardware físico
# ─────────────────────────────────────────────────────────────────────────────

class SimuladorMedidor:
    """
    Genera lecturas realistas de un medidor Red Seal para pruebas.

    Simula:
      - Flujo con ruido gaussiano alrededor de una base
      - Totalizador acumulativo coherente con el flujo y la frecuencia de lectura
      - Temperatura y presión estables con pequeñas variaciones
      - Ocasionalmente (1% de probabilidad) genera un pico de flujo para probar alertas

    Uso:
        sim = SimuladorMedidor("SIM-CORIOLIS-01", flujo_base_lpm=150.0)
        for _ in range(10):
            lectura = sim.leer()
            print(lectura.to_json())
            time.sleep(5)
    """

    def __init__(
        self,
        medidor_id:          str   = "SIM-001",
        flujo_base_lpm:      float = 150.0,
        temp_base:           float = 20.0,
        presion_base:        float = 101.3,
        totalizador_inicial: float = 50_000.0,
        intervalo_seg:       float = 5.0,
    ):
        self.medidor_id    = medidor_id
        self.flujo_base    = flujo_base_lpm
        self.temp_base     = temp_base
        self.presion_base  = presion_base
        self._totalizador  = totalizador_inicial
        self._intervalo    = intervalo_seg
        self._ultimo_tick  = time.monotonic()

    def leer(self) -> LecturaMedidor:
        """Genera una lectura simulada."""
        import random

        # Tiempo transcurrido para calcular incremento real del totalizador
        now  = time.monotonic()
        dt   = now - self._ultimo_tick
        self._ultimo_tick = now

        # Flujo con ruido ±5% y ocasional pico
        ruido = random.gauss(0, self.flujo_base * 0.02)
        pico  = random.gauss(self.flujo_base * 2, 10) if random.random() < 0.01 else 0
        flujo = max(0.0, self.flujo_base + ruido + pico)

        # Totalizador: flujo (L/min) × tiempo (min)
        self._totalizador += flujo * (dt / 60.0)

        return LecturaMedidor(
            medidor_id        = self.medidor_id,
            timestamp         = datetime.now(timezone.utc).isoformat(),
            flujo_instantaneo = round(flujo, 4),
            totalizador       = round(self._totalizador, 3),
            temperatura       = round(self.temp_base + random.gauss(0, 0.15), 2),
            presion           = round(self.presion_base + random.gauss(0, 0.3), 2),
            fuente            = "simulador",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. BUCLE DE LECTURA PERIÓDICA (para integrar como hilo de fondo)
# ─────────────────────────────────────────────────────────────────────────────

def iniciar_lectura_periodica(
    host:        str,
    medidor_id:  str,
    db_path:     str,
    intervalo:   float = 60.0,   # segundos entre lecturas
    unit_id:     int   = 1,
    usar_mock:   bool  = False,  # True = usar simulador en lugar de hardware real
) -> None:
    """
    Bucle infinito que lee el medidor cada `intervalo` segundos y guarda en DB.
    Ejecutar en un hilo separado (threading.Thread) o proceso aparte.

    Ejemplo en main.py:
        import threading
        from services.modbus_reader import iniciar_lectura_periodica

        t = threading.Thread(
            target=iniciar_lectura_periodica,
            args=("192.168.1.100", "CORIOLIS-01", "storage/data.db"),
            kwargs={"intervalo": 60, "usar_mock": False},
            daemon=True,
        )
        t.start()
    """
    logger.info(
        "Iniciando lectura periódica: medidor=%s host=%s intervalo=%ds mock=%s",
        medidor_id, host, int(intervalo), usar_mock,
    )
    sim = SimuladorMedidor(medidor_id=medidor_id) if usar_mock else None

    while True:
        try:
            if usar_mock and sim:
                lectura = sim.leer()
            else:
                lectura = leer_medidor(host=host, medidor_id=medidor_id, unit_id=unit_id)

            valida = guardar_lectura(lectura, db_path)
            logger.info(
                "Lectura %s — flujo=%.2f L/min  total=%.1f L  temp=%.1f°C  válida=%s",
                medidor_id, lectura.flujo_instantaneo, lectura.totalizador,
                lectura.temperatura, valida,
            )
        except ConnectionError as e:
            logger.error("Error de conexión Modbus (%s): %s — reintentando en %ds", medidor_id, e, int(intervalo))
        except Exception as e:
            logger.exception("Error inesperado en lectura de %s: %s", medidor_id, e)

        time.sleep(intervalo)
