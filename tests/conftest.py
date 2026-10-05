def pytest_addoption(parser):
    parser.addoption('--actualizar-esperados', action='store_true',
                     help='guardar el resultado actual del conversor como esperado en muestras/<nombre>/esperado/ '
                          '(después revisar a mano los resumen.json que cambiaron)')
