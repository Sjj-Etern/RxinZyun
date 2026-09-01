class PatientModel {
  final int id;
  final String name;
  final int age;
  final String gender; // 男, 女
  final String medicalRecordNo;
  final String? phone;

  PatientModel({
    required this.id,
    required this.name,
    required this.age,
    required this.gender,
    required this.medicalRecordNo,
    this.phone,
  });

  factory PatientModel.fromJson(Map<String, dynamic> json) {
    return PatientModel(
      id: json['id'] as int,
      name: json['name'] as String,
      age: json['age'] as int,
      gender: json['gender'] as String,
      medicalRecordNo: (json['medical_record_no'] ?? json['id_card'] ?? '') as String,
      phone: json['phone'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'age': age,
      'gender': gender,
      'medical_record_no': medicalRecordNo,
      'phone': phone,
    };
  }
}
