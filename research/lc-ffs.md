# DKmode research — LC / FFS

**Статус: HISTORICAL REFERENCE / DESIGN, не готовый модуль DKmode.**

Первичные источники:
- [Launch Control / v68–v69](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/launch-control-spark-cut.md)
- [FFS / v85](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/v85-ffs-spark-cut.md)
- [MerpMod address references](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/merpmod-a2wc012e-address-map.md)

## Переносимые идеи

- **Состояние** LC/FFS, **целевая частота RPM** и **исполнительный механизм ограничения** (fuel/spark) — разные сущности. Их не следует смешивать.
- Normal hard redline остаётся независимой штатной защитой.
- Приоритеты LC / FFS / обычного ограничителя должны иметь явную таблицу переходов и условия сброса.
- Значения в RAM и hooks нельзя принимать на веру по названию переменной: нужны дизассемблирование и лог.

## Исторические наблюдения

- В эксперименте v68 LC с новым режимом сохранялась компонента fuel cut: в логе IPW периодически падал примерно до 0.77 ms.
- Для v69 предлагался clean spark path; в первичном документе статус **EXPERIMENTAL / awaiting validation**.
- Для v85 документирована экспериментальная FFS spark-cut архитектура. Не считать её подтверждённым DKmode решением.

## Требования к исследованию DKmode

1. Определить все штатные и MerpMod ветви управления RPM limiter.
2. Изучить event timing, OCR/GR hooks, сохранение контекста и безопасные границы.
3. Документировать кто владеет `RevLimCut/Resume` в каждом состоянии.
4. Проверить, что выход из LC/FFS не оставляет изменённые активные пороги или spark flags.
5. Изолировать поведение hard redline, fuel/spark и transient fueling.
6. Ввести отдельные проверки checksum/diff и процедурный rollback.

Пока это лишь набор требований; включать в сборку без верификации нельзя.
