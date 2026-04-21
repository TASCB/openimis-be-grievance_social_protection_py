from django.contrib import admin
from .models import GrievanceType, GrievanceCategory, GrievanceChannel


@admin.register(GrievanceCategory)
class GrievanceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name",)


@admin.register(GrievanceType)
class GrievanceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "code", "is_active")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(GrievanceChannel)
class GrievanceChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name",)
