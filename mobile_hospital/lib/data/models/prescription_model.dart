class PrescriptionModel {
  final int id;
  final String prescriptionCode;
  final int patientId;
  final int doctorId;
  final String status; // pending, approved, rejected, dispensing, completed
  final String createdAt;
  final String? patientName;
  final String? patientGender;
  final int? patientAge;
  final String? doctorName;
  final String? diagnosis;
  final List<PrescriptionItemModel> items;

  PrescriptionModel({
    required this.id,
    required this.prescriptionCode,
    required this.patientId,
    required this.doctorId,
    required this.status,
    required this.createdAt,
    this.patientName,
    this.patientGender,
    this.patientAge,
    this.doctorName,
    this.diagnosis,
    required this.items,
  });

  factory PrescriptionModel.fromJson(Map<String, dynamic> json) {
    var itemsList = json['items'] as List? ?? [];
    List<PrescriptionItemModel> parsedItems = itemsList
        .map((i) => PrescriptionItemModel.fromJson(i as Map<String, dynamic>))
        .toList();

    return PrescriptionModel(
      id: json['id'] as int,
      prescriptionCode: json['prescription_code'] as String,
      patientId: json['patient_id'] as int,
      doctorId: json['doctor_id'] as int,
      status: json['status'] as String,
      createdAt: json['created_at'] as String,
      patientName: json['patient_name'] as String?,
      patientGender: json['patient_gender'] as String?,
      patientAge: json['patient_age'] as int?,
      doctorName: json['doctor_name'] as String?,
      diagnosis: json['diagnosis'] as String?,
      items: parsedItems,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'prescription_code': prescriptionCode,
      'patient_id': patientId,
      'doctor_id': doctorId,
      'status': status,
      'created_at': createdAt,
      'patient_name': patientName,
      'patient_gender': patientGender,
      'patient_age': patientAge,
      'doctor_name': doctorName,
      'diagnosis': diagnosis,
      'items': items.map((i) => i.toJson()).toList(),
    };
  }

  String get statusText {
    switch (status) {
      case 'pending':
        return '待发药';
      case 'approved':
        return '待发药';
      case 'rejected':
        return '已驳回';
      case 'dispensing':
        return '配药中';
      case 'completed':
        return '已完成';
      default:
        return status;
    }
  }
}

class PrescriptionItemModel {
  final int id;
  final int medicineId;
  final String? dosage;
  final String? usageMethod;
  final String? frequency;
  final int? days;
  final int quantity;
  final String? note;
  final String? medicineName;
  final String? specification;
  final String? manufacturer;
  final String? unit;
  final String? traceCode;
  final String? traceStatus; // pending, scanned_identify, scanned_outbound, scanned_confirm
  final String? scan1Time;
  final String? scan2Time;
  final String? scan3Time;

  PrescriptionItemModel({
    required this.id,
    required this.medicineId,
    this.dosage,
    this.usageMethod,
    this.frequency,
    this.days,
    required this.quantity,
    this.note,
    this.medicineName,
    this.specification,
    this.manufacturer,
    this.unit,
    this.traceCode,
    this.traceStatus,
    this.scan1Time,
    this.scan2Time,
    this.scan3Time,
  });

  factory PrescriptionItemModel.fromJson(Map<String, dynamic> json) {
    return PrescriptionItemModel(
      id: json['id'] as int,
      medicineId: json['medicine_id'] as int,
      dosage: json['dosage'] as String?,
      usageMethod: json['usage_method'] as String?,
      frequency: json['frequency'] as String?,
      days: json['days'] as int?,
      quantity: json['quantity'] as int? ?? 1,
      note: json['note'] as String?,
      medicineName: json['medicine_name'] as String?,
      specification: json['specification'] as String?,
      manufacturer: json['manufacturer'] as String?,
      unit: json['unit'] as String?,
      traceCode: json['trace_code'] as String?,
      traceStatus: json['trace_status'] as String?,
      scan1Time: json['scan1_time'] as String?,
      scan2Time: json['scan2_time'] as String?,
      scan3Time: json['scan3_time'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'medicine_id': medicineId,
      'dosage': dosage,
      'usage_method': usageMethod,
      'frequency': frequency,
      'days': days,
      'quantity': quantity,
      'note': note,
      'medicine_name': medicineName,
      'specification': specification,
      'manufacturer': manufacturer,
      'unit': unit,
      'trace_code': traceCode,
      'trace_status': traceStatus,
      'scan1_time': scan1Time,
      'scan2_time': scan2Time,
      'scan3_time': scan3Time,
    };
  }

  String get traceStatusText {
    if (traceStatus == null) return '未绑定追溯码';
    switch (traceStatus) {
      case 'pending':
        return '待扫描';
      case 'scanned_identify':
        return '已识别/配药中';
      case 'scanned_outbound':
        return '已出库/配送中';
      case 'scanned_confirm':
        return '已确认收药';
      default:
        return '未知';
    }
  }
}
