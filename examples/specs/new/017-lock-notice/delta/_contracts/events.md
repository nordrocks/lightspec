## events.account-locked
Изменение: MODIFIED
Источник: feature:007-login-lockout
Причина: None
Тип: событие
Данные: contract:events.account-locked-data

Аккаунт заблокирован после неудачных входов. Отправляется и для письма пользователю.

### Гарантии

- доставка: хотя бы один раз

### Формат

- топик `account-events`, ключ — `accountId`
