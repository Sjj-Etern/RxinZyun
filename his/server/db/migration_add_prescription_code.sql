-- Migration: Add prescription_code column to prescriptions table
-- Run this manually on the HIS MySQL database (192.168.51.133 / database: test)
--
--   mysql -h 192.168.51.133 -u root -p test < migration_add_prescription_code.sql

ALTER TABLE prescriptions ADD COLUMN prescription_code VARCHAR(30) DEFAULT NULL AFTER id;
