## events.account-locked
Изменение: ADDED
Источник: None
Причина: None
Тип: событие
Данные: contract:events.account-locked-data

Аккаунт заблокирован после неудачных входов.

### Гарантии

- доставка: хотя бы один раз

### Формат

- топик `account-events`, ключ — `accountId`

## events.account-locked-data
Изменение: ADDED
Источник: None
Причина: None
Тип: модель

Какой аккаунт заблокирован и до какого времени.

### Поля

| Поле | Тип | Формат | Обязательно | Описание |
|---|---|---|---|---|
| accountId | string | UUID | да | ID аккаунта |
| lockedUntil | datetime | ISO 8601, UTC: `2026-10-26T14:35:00Z` | да | время разблокировки |
