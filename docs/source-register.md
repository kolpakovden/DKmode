# DKmode — реестр первоисточников

Идеи DKmode могут опираться на исследования прежнего проекта, но **их достоверность всегда ограничена конкретным ROM, кодом и измерениями**.

| ID | Источник | Что берём | Статус для DKmode |
| --- | --- | --- | --- |
| F-001 | [A2WC012E map](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/a2wc012e-map.md) | Проверенные calibration offsets и правила проверки адресов | REFERENCE до проверки на точной базе DKmode |
| F-002 | [MerpMod address map](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/merpmod-a2wc012e-address-map.md) | ROM/code hooks, RAM pointers, исходные гипотезы по свободной памяти | REFERENCE; отдельная проверка map/disassembly |
| F-003 | [SD transient fueling vs CarBerry](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/sd-transient-fueling.md) | Исследование Tip-in/SD и сравнение поведения CarBerry 4.2 | Сравнение данных подтверждено в конкретных BIN; причинная связь lean spike — HYPOTHESIS |
| F-004 | [LC spark cut](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/launch-control-spark-cut.md) | LC/FFS интерфейсы и наблюдения mixed fuel/spark cut | v68 vehicle evidence; v69 experimental в исходном документе |
| F-005 | [FFS v85](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/v85-ffs-spark-cut.md) | История FFS spark-cut и ограничение старого подхода | EXPERIMENTAL / требуется повторная проверка перед повторным использованием |
| F-006 | [Research backlog](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/research-backlog.md) | Неисследованные вопросы и требования к тестам | HYPOTHESIS/REFERENCE |
| F-007 | [Known results](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/known-results.md) | Наблюдения и проверенные на автомобиле факты | Историческое evidence; не DKmode validation |

## Проверенные исходные образцы из F-003 (пока только ссылки)

### Forester clean v25

- File: `Forester_SG9_MAP_clean_v25.bin`
- Size: `524288` bytes
- SHA-256: `2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99`
- Platform: SH7055, patched ROM ID A2WC0MME

### CarBerry 4.2 reference

- File: `work2_100+95_3D04EA4605_CarBerry42_FULL_160KiB.bin`
- Size: `163840` bytes
- SHA-256: `b06e1282a4b274db856d250ae8a1babaf175729f7e9fec12e465fb774a4483`
- Platform: 68HC16Y5, ECU ID 3D04EA4605

### Forester v84 AF_off — **proposed, not verified DKmode baseline**

- File: `forester_sg9_sti_MAP_IAT_GM_dMap_v84_AF_off.bin`
- SHA-256: `30b1994039775bbef362bcd166d6fcfbde3d618585115a7a44edeb53f3bae278`
- Размер по историческому описанию: 524288 байт
- Источник: [v85 FFS research](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/v85-ffs-spark-cut.md)
- Файл v84 **не обнаружен в индексированном дереве старого репозитория при первоначальном аудите**. До получения и независимой сверки **не использовать его как фактическую входную базу сборки DKmode**.

## Важные несовпадения

- A2WC012E, A2WC0MME и другие внутренние ROM IDs не означают идентичность всех адресов.
- `dRomHoleStart = 0x69C10` — ориентир из MerpMod, но **не доказательство**, что любой диапазон после него свободен.
- `0x6A378` в clean v25 относится к Atmospheric Pressure Compensation, не к Delta MAP table.
- Наличие `pDeltaMap` в reference address map не доказывает его использование в конкретной сборке.

## Условия добавления новых записей

Указывать URL/commit/source revision, platform, ROM/ECU ID, хеш BIN, уровень подтверждения, чем доказано, ограничение и дальнейший тест. Фактический новый результат записывается здесь после проверки.
