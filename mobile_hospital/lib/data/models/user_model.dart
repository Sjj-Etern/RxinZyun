class UserModel {
  final int id;
  final String username;
  final String realName;
  final String role; // doctor, pharmacist, admin

  UserModel({
    required this.id,
    required this.username,
    required this.realName,
    required this.role,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] as int,
      username: json['username'] as String,
      realName: json['real_name'] as String,
      role: json['role'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'real_name': realName,
      'role': role,
    };
  }

  bool get isDoctor => role == 'doctor' || role == 'admin';
  bool get isPharmacist => role == 'pharmacist' || role == 'admin';
  bool get isAdmin => role == 'admin';
}
