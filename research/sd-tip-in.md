# DKmode research — SD / transient fueling / Tip-in

**Статус: SOURCE ANALYSIS + HYPOTHESIS. DKmode-реализации пока нет.**

Первичный анализ: [forester_A2WC012E/docs/sd-transient-fueling.md](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/sd-transient-fueling.md). Сравнение относится к конкретным historical BIN из [реестра источников](../docs/source-register.md), а не ко всем CarBerry или всем Forester.

## Что уже видно из исследования

- Обе системы используют отдельный путь Throttle Tip-in Enrichment.
- В исследованном CarBerry 4.2 reference Minimum Tip-in Activation ~**0.384 ms**.
- В исследованном Forester clean v25 — **1.000 ms** (`0x58DA8` в этом конкретном BIN).
- При нейтральных компенсациях типовая таблица проходит threshold примерно при **2.2% Delta TPS** в CarBerry и **6.2% Delta TPS** в Forester.
- Из этого **не следует**, что CarBerry можно прямо скопировать в DKmode или что 0.384 ms безопасно для нашей аппаратной конфигурации.

## Гипотеза

В умеренных transient-режимах низкий рассчитанный Tip-in pulse может отбрасываться из-за порога, создавая lean spike. В историческом исследовании возможен controlled test `1.000 -> 0.600 ms`, затем отдельный `0.500 ms` при положительном результате. Это **план исследования прошлой прошивки**, не готовое значение DKmode.

## Требования к будущему DKmode-модулю

- Диагностика activation state и рассчитанного/применённого Tip-in pulse.
- Подтверждение расчёта transient fuel и связи с steady-state VE.
- Явная проверка компенсаций ECT/RPM/boost-error и влияния injector scaling.
- Переключаемый независимый модуль, без побочных поправок VE.
- Возможность документированного A/B теста с контрольным логированием.

## Критерии evidence

Нужны baseline и test с одинаковым прогретым режимом, передачей, стартовым RPM и профилем педали; логировать RPM, throttle/Delta TPS, MAP, IPW, WB AFR/lambda, load, ECT/IAT, trims и доступные transient counters. Успех — меньше lean spike без rich spike/рывка/изменения steady-state.

## Неясности

- Какая фактическая baseline ROM будет использоваться для DKmode?
- Подтверждены ли hook, память и сигнатура Tip-in в этой сборке?
- Какой runtime parameter реально доступен в logger?
- Влияет ли несовпадение железа/форсунок на наблюдаемую разницу?

До устранения этих неизвестных — **исследование, не патч**.
