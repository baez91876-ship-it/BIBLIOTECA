"""Pruebas de validadores Pydantic para valores opcionales y límites."""

import pytest
from pydantic import ValidationError

from app.schemas.autor import AutorCreate, AutorPatch
from app.schemas.categoria import CategoriaCreate, CategoriaPatch
from app.schemas.libro import LibroCreate, LibroPatch, _validar_categoria_ids
from app.schemas.socio import SocioCreate, SocioPatch


def test_author_normalization_and_optional_patch_fields():
    author = AutorCreate(nombre="  ana   lopez ", nacionalidad="  Costa   Rica ")
    assert author.nombre == "Ana Lopez"
    assert author.nacionalidad == "Costa Rica"
    assert AutorCreate(nombre="Ana").nacionalidad is None
    with pytest.raises(ValidationError):
        AutorPatch(nombre=None)
    assert AutorPatch(nacionalidad=None).anio_nacimiento is None
    with pytest.raises(ValueError, match="no puede ser nulo"):
        AutorPatch.model_construct(
            _fields_set={"nombre"}, nombre=None
        ).validar_campos_requeridos()


def test_category_normalization_and_required_patch_name():
    assert CategoriaCreate(nombre="  NOVELA  ").nombre == "novela"
    with pytest.raises(ValidationError):
        CategoriaPatch(nombre=None)
    assert CategoriaPatch(descripcion=None).nombre is None
    with pytest.raises(ValueError, match="no puede ser nulo"):
        CategoriaPatch.model_construct(
            _fields_set={"nombre"}, nombre=None
        ).validar_campos_requeridos()


def test_book_category_bounds_and_optional_patch_values():
    with pytest.raises(ValueError, match="entre 1 y 5"):
        _validar_categoria_ids([])
    with pytest.raises(ValueError, match="entre 1 y 5"):
        _validar_categoria_ids([1, 2, 3, 4, 5, 6])
    assert _validar_categoria_ids([1, 2]) == [1, 2]
    with pytest.raises(ValueError):
        _validar_categoria_ids([1, 1])
    with pytest.raises(ValidationError):
        LibroPatch(titulo=None)
    assert LibroPatch().categoria_ids is None
    with pytest.raises(ValidationError):
        LibroCreate(
            titulo="Libro",
            isbn="9780000000001",
            anio_publicacion=2020,
            ejemplares=1,
            autor_id=1,
            categoria_ids=[1, 1],
        )


def test_member_optional_fields_and_telephone_validation():
    assert (
        SocioCreate(
            nombre="ana lopez",
            email="ANA@example.com",
        ).email
        == "ana@example.com"
    )
    assert (
        SocioCreate(
            nombre="ana lopez",
            email="ana@example.com",
            telefono=None,
        ).telefono
        is None
    )
    assert SocioPatch(telefono=None).telefono is None
    with pytest.raises(ValidationError):
        SocioPatch(email=None)
    with pytest.raises(ValidationError):
        SocioCreate(
            nombre="Ana",
            email="ana@example.com",
            telefono="123-4567",
        )
    with pytest.raises(ValidationError):
        SocioPatch(nombre=None)
    with pytest.raises(ValidationError):
        SocioPatch(telefono="123-4567")
