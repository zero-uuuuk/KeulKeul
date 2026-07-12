DROP TABLE IF EXISTS keulkeul.club_members;

CREATE TABLE keulkeul.club_members (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(100) NOT NULL,
  title VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL DEFAULT NULL,
  CONSTRAINT chk_club_members_title CHECK (title IN ('president', 'vice_president', 'member'))
);

INSERT INTO keulkeul.club_members (user_id, name, title, status)
VALUES
  ('younguk', 'Younguk', 'president', 'active'),
  ('yujin', 'Yujin', 'vice_president', 'active'),
  ('hyundo', 'Hyundo', 'member', 'active'),
  ('juhyun', 'Juhyun', 'member', 'active'),
  ('taeho', 'Taeho', 'member', 'active'),
  ('munho', 'Munho', 'member', 'active'),
  ('suha', 'Suha', 'member', 'active'),
  ('taehwan', 'Taehwan', 'member', 'active'),
  ('hyunryeo', 'Hyunryeo', 'member', 'active');

SELECT id, user_id, name, title, status, created_at
FROM keulkeul.club_members
ORDER BY id;

SELECT id, user_id, name, title, status
FROM keulkeul.club_members
WHERE title = 'president';

SELECT id, user_id, name, title, status
FROM keulkeul.club_members
WHERE title = 'member'
ORDER BY id;

UPDATE keulkeul.club_members
SET title = 'member',
    updated_at = CURRENT_TIMESTAMP
WHERE user_id = 'younguk';

SELECT id, user_id, name, title, status, updated_at
FROM keulkeul.club_members
WHERE user_id = 'younguk';

DELETE FROM keulkeul.club_members
WHERE user_id = 'hyunryeo';

SELECT id, user_id, name, title, status
FROM keulkeul.club_members
ORDER BY id;
