let deliverySchemaReady = false;

export async function ensureDeliverySchema(conn: any): Promise<void> {
  if (deliverySchemaReady) return;

  await conn.query(`CREATE TABLE IF NOT EXISTS face_profiles (
    id INT NOT NULL AUTO_INCREMENT, user_id INT NOT NULL, face_image MEDIUMTEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_face_profiles_user (user_id),
    CONSTRAINT fk_face_profiles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  await conn.query(`CREATE TABLE IF NOT EXISTS robots (
    id INT NOT NULL AUTO_INCREMENT, code VARCHAR(50) NOT NULL, name VARCHAR(100) NOT NULL,
    status ENUM('available','busy','disabled') NOT NULL DEFAULT 'available',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_robots_code (code)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  await conn.query(`INSERT IGNORE INTO robots (code, name, status) VALUES
    ('R001', '配送机器人 1 号', 'available'), ('R002', '配送机器人 2 号', 'available')`);
  await conn.query(`CREATE TABLE IF NOT EXISTS delivery_records (
    id INT NOT NULL AUTO_INCREMENT, prescription_id INT NOT NULL, prescription_item_id INT NOT NULL,
    robot_id INT NOT NULL, status ENUM('delivering','arrived','unlocked') NOT NULL DEFAULT 'delivering',
    dispatched_by INT NOT NULL, verified_by INT NULL, dispatched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    arrived_at DATETIME NULL, unlocked_at DATETIME NULL, PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_prescription_item (prescription_item_id), KEY idx_delivery_prescription (prescription_id),
    KEY idx_delivery_robot (robot_id), KEY idx_delivery_status (status),
    CONSTRAINT fk_delivery_prescription FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT,
    CONSTRAINT fk_delivery_item FOREIGN KEY (prescription_item_id) REFERENCES prescription_items(id) ON DELETE RESTRICT,
    CONSTRAINT fk_delivery_robot FOREIGN KEY (robot_id) REFERENCES robots(id) ON DELETE RESTRICT,
    CONSTRAINT fk_delivery_dispatcher FOREIGN KEY (dispatched_by) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_delivery_verifier FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  deliverySchemaReady = true;
}
