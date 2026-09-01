class MedicineModel {
  final int id;
  final String name;
  final String? genericName;
  final String? specification;
  final String? drugForm;
  final String? manufacturer;
  final String unit;
  final double price;
  final int stock;
  final String? category;
  final int isNarcotic; // 0: 否, 1: 是
  final String? imageUrl;
  final String? traceCodePrefix;

  MedicineModel({
    required this.id,
    required this.name,
    this.genericName,
    this.specification,
    this.drugForm,
    this.manufacturer,
    required this.unit,
    required this.price,
    required this.stock,
    this.category,
    required this.isNarcotic,
    this.imageUrl,
    this.traceCodePrefix,
  });

  factory MedicineModel.fromJson(Map<String, dynamic> json) {
    return MedicineModel(
      id: json['id'] as int,
      name: json['name'] as String,
      genericName: json['generic_name'] as String?,
      specification: json['specification'] as String?,
      drugForm: json['drug_form'] as String?,
      manufacturer: json['manufacturer'] as String?,
      unit: json['unit'] as String? ?? '盒',
      price: double.tryParse(json['price']?.toString() ?? '0') ?? 0.0,
      stock: json['stock'] as int? ?? 0,
      category: json['category'] as String?,
      isNarcotic: json['is_narcotic'] as int? ?? 0,
      imageUrl: json['image_url'] as String?,
      traceCodePrefix: json['trace_code_prefix'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'generic_name': genericName,
      'specification': specification,
      'drug_form': drugForm,
      'manufacturer': manufacturer,
      'unit': unit,
      'price': price,
      'stock': stock,
      'category': category,
      'is_narcotic': isNarcotic,
      'image_url': imageUrl,
      'trace_code_prefix': traceCodePrefix,
    };
  }

  bool get isNarcoticBool => isNarcotic == 1;
}
