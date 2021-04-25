from setuptools import setup


def read(filename):
    try:
        with open(filename, 'r') as f:
            return f.read()
    except IOError:
        return ''


setup(
    name='construct-utils',
    version='0.0.1',
    description='Some useful Construct utility classes',
    long_description=read('README.md'),
    author='shiftinv',
    url='https://github.com/shiftinv/construct-utils',
    license='Apache 2.0',
    packages=['constructutils'],
    install_requires=read('requirements.txt').splitlines(),
    extras_require={
        'dev': ['pytest', 'pytest-cov']
    },
    python_requires='>=3.7',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities'
    ]
)
