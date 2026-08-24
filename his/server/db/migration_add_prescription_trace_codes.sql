-- Migration: Add prescription to trace-code association table
-- Run after migration_add_prescription_id.sql if medicine_trace_codes.prescription_id
-- does not exist in the target database yet.

CREATE TABLE IF NOT EXISTS `prescription_trace_codes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `prescription_id` int NOT NULL COMMENT '关联处方ID',
  `prescription_item_id` int NOT NULL COMMENT '关联处方药品明细ID',
  `medicine_id` int NOT NULL COMMENT '关联药品ID',
  `trace_code_id` int NOT NULL COMMENT '关联追溯码ID',
  `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `uk_trace_code_id` (`trace_code_id` ASC) USING BTREE,
  UNIQUE INDEX `uk_prescription_trace_code` (`prescription_id` ASC, `trace_code_id` ASC) USING BTREE,
  INDEX `idx_prescription_id` (`prescription_id` ASC) USING BTREE,
  INDEX `idx_prescription_item_id` (`prescription_item_id` ASC) USING BTREE,
  INDEX `idx_medicine_id` (`medicine_id` ASC) USING BTREE,
  CONSTRAINT `prescription_trace_codes_ibfk_1` FOREIGN KEY (`prescription_id`) REFERENCES `prescriptions` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `prescription_trace_codes_ibfk_2` FOREIGN KEY (`prescription_item_id`) REFERENCES `prescription_items` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `prescription_trace_codes_ibfk_3` FOREIGN KEY (`medicine_id`) REFERENCES `medicines` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `prescription_trace_codes_ibfk_4` FOREIGN KEY (`trace_code_id`) REFERENCES `medicine_trace_codes` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;
