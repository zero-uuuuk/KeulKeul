CREATE DATABASE IF NOT EXISTS keulkeul;

USE keulkeul;

CREATE TABLE IF NOT EXISTS todos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  completed BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO todos (title, completed)
SELECT 'Docker Compose 학습', FALSE
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1
  FROM todos
  WHERE title = 'Docker Compose 학습'
);

INSERT INTO todos (title, completed)
SELECT 'MySQL 연결 확인', FALSE
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1
  FROM todos
  WHERE title = 'MySQL 연결 확인'
);

