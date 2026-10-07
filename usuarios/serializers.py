from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from catalogos.models import Cliente
from usuarios.models import Rol, Usuario


class UsuarioBreveSerializer(serializers.ModelSerializer):
    rol = serializers.CharField(source="rol_nombre", read_only=True)

    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "apellido", "documento", "rol"]


class UsuarioSerializer(serializers.ModelSerializer):
    rol = serializers.SlugRelatedField(slug_field="nombre", queryset=Rol.objects.all())
    cliente_id = serializers.PrimaryKeyRelatedField(
        source="cliente",
        queryset=Cliente.objects.all(),
        allow_null=True,
        required=False,
    )
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "password",
            "nombre",
            "apellido",
            "telefono",
            "documento",
            "rol",
            "cliente_id",
            "is_active",
        ]

    def validate(self, attrs):
        rol = attrs.get("rol", getattr(self.instance, "rol", None))
        if "cliente" in attrs:
            cliente = attrs.get("cliente")
        else:
            cliente = getattr(self.instance, "cliente", None)
        if rol and rol.nombre == Rol.Nombre.CLIENTE and cliente is None:
            raise serializers.ValidationError({"cliente_id": ["El usuario cliente debe pertenecer a un cliente."]})
        if rol and rol.nombre != Rol.Nombre.CLIENTE and cliente is not None:
            raise serializers.ValidationError({"cliente_id": ["Solo el rol CLIENTE lleva un cliente."]})
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": ["La clave es obligatoria."]})
        password = attrs.get("password")
        if password:
            try:
                validate_password(password)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        documento = attrs.get("documento", getattr(self.instance, "documento", ""))
        if documento is not None and not str(documento).strip():
            raise serializers.ValidationError({"documento": ["El documento es obligatorio."]})
        email = attrs.get("email", getattr(self.instance, "email", ""))
        if not str(email or "").strip():
            raise serializers.ValidationError({"email": ["El correo es obligatorio."]})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data["email"] = validated_data["email"].strip().lower()
        validated_data["username"] = validated_data["email"]
        usuario = Usuario(**validated_data)
        usuario.set_password(password)
        usuario.save()
        return usuario

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if "email" in validated_data:
            validated_data["email"] = validated_data["email"].strip().lower()
            validated_data["username"] = validated_data["email"]
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
