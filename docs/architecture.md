# DKmode — архитектура (проектный эскиз)

**Статус: DESIGN / не реализация.** Никаких бинарных DKmode патчей этим документом не заявляется.

```text
Exact baseline ROM + SHA-256
            |
            v
Target profile (CPU, ROM ID, memory map, RAM symbols)
            |
            v
Selected independent modules
     |       |        |
    SD    LC/FFS   Diagnostics ...
     \       |      /
      Integration planner
       - ROM/RAM allocation
       - hook ownership
       - dependency/conflict checks
            |
            v
Deterministic patch/build
            |
            v
Automated static validation
            |
            v
EXPERIMENTAL BIN + manifest + reversible diff
            |
            v
Bench verification -> guarded vehicle logging -> VALIDATED
```

## Target profile

У каждого ROM-target отдельный файл с:
- CPU, точным ROM ID и идентификатором сборки;
- длиной и SHA-256 базового BIN;
- сегментами ROM, entry points и проверенными code hooks;
- RAM symbols с datatype, endian, lifetime/ownership;
- правилами checksum и шагами flashing/rollback;
- набором поддерживаемых модулей и их preconditions.

**Нельзя** трактовать адрес из одного target как подтверждённый для другого.

## Контракт модуля

Каждый модуль должен описывать:
1. цели, режимы включения и условия выхода;
2. входные/выходные сигналы, RAM и ROM allocations;
3. перехватываемые функции, ABI, сохранение регистров, инструкции-трамплины;
4. связи с остальными модулями и возможные конфликты;
5. fallback/stock behaviour, безопасные ограничения;
6. набор статических проверок и контрольных логов;
7. уровень подтверждения и известные ограничения.

## Правила интеграции

- Одинаковый hook не может молча принадлежать двум модулям.
- Обязательны явные правила приоритета LC, FFS и normal hard redline.
- Существующая штатная защита двигателя не должна исчезать из-за локальной функции.
- Проектировщик проверяет выход за ROM-size, пересечение секций и изменение байтов вне ожидаемого diff.
- Изменения checksum выполняются по отдельно верифицированной процедуре и проверяются после сборки.
- Статические тесты **не заменяют** проверки на стенде и в машине.

## Исходная точка

Следующий технический этап — получить точный verified BIN (v84 кандидат, но файл пока не подтверждён), зафиксировать оригинальный base hash и собрать минимальный reproducible no-op workflow. Только после этого подключать экспериментальные функции.
