import 'package:flutter_test/flutter_test.dart';
import 'package:his_mobile/data/models/prescription_model.dart';

void main() {
  test('处方模型按网页端状态和多追溯码结构解析', () {
    final prescription = PrescriptionModel.fromJson({
      'id': 12,
      'prescription_code': 'RX-0012',
      'patient_id': 3,
      'doctor_id': 5,
      'status': 'dispensed',
      'created_at': '2026-09-12 10:00:00',
      'items': [
        {
          'id': 21,
          'medicine_id': 8,
          'quantity': 2,
          'medicine_name': '测试药品',
          'trace_codes': [
            {
              'trace_code': '12345670000000000001',
              'trace_status': 'scanned_confirm',
              'scan1_time': null,
              'scan2_time': '2026-09-12 10:01:00',
              'scan3_time': '2026-09-12 10:02:00',
            },
            {
              'trace_code': '12345670000000000002',
              'trace_status': 'scanned_outbound',
              'scan1_time': null,
              'scan2_time': '2026-09-12 10:03:00',
              'scan3_time': null,
            },
          ],
        },
      ],
    });

    expect(prescription.statusText, '已发药');
    expect(prescription.items.single.traceCodes, hasLength(2));
    expect(prescription.items.single.traceStatus, 'scanned_outbound');
    expect(
      prescription.items.single.traceCode,
      '12345670000000000001、12345670000000000002',
    );
  });
}
