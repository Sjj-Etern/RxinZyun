-- 为 medicine_trace_codes 表新增 prescription_id 字段
-- 用于关联追溯码扫码记录到具体处方

ALTER TABLE `medicine_trace_codes`
  ADD COLUMN `prescription_id` int DEFAULT NULL COMMENT '关联处方ID' AFTER `medicine_id`,
  ADD INDEX `idx_prescription_id` (`prescription_id`),
  ADD CONSTRAINT `medicine_trace_codes_ibfk_prescription`
    FOREIGN KEY (`prescription_id`) REFERENCES `prescriptions` (`id`)
    ON DELETE SET NULL ON UPDATE RESTRICT;
