/*
 * pcmseqio.c
 *
 * A python extension module that provides IO for the pcm_seq2 file format.
 * Data are stored in numpy arrays.
 *
 */

#include <Python.h>

#include "numpy/arrayobject.h"
#include "pcmio.h"

typedef struct {
	PyObject_HEAD
	PCMFILE *pfp;
} PcmfileObject;

/* destructor */
static void
pcmfile_dealloc(PcmfileObject* self) 
{
	if (self->pfp)
		pcm_close(self->pfp);
	self->ob_type->tp_free((PyObject*)self);
}

/* ctor */
static int
pcmfile_init(PcmfileObject* self, PyObject* args)
{
	char *filename;
	char *mode = "r";

	if (!PyArg_ParseTuple(args, "s|s", &filename, &mode))
		return -1;

	if (self->pfp)
		pcm_close(self->pfp);

	if ((self->pfp = pcm_open(filename, mode)) == NULL) {
		PyErr_SetString(PyExc_IOError, "Unable to open file");
		return -1;
	}

	return 0;
}

/* methods */

static PyObject*
pcmfile_nentries(PcmfileObject* self, void *closure)
{
	return Py_BuildValue("i", self->pfp->nentries);
}

static PyObject*
pcmfile_timestamp(PcmfileObject* self, void *closure)
{
	struct pcmstat s;
	pcm_stat(self->pfp, &s);
	return Py_BuildValue("i", s.timestamp);
}

static int
pcmfile_settimestamp(PcmfileObject* self, PyObject *value, void *closure)
{
	int timestamp;
	if (value == NULL) {
		PyErr_SetString(PyExc_TypeError, "Cannot delete the timestamp attribute");
		return -1;
	}

	timestamp = (int)PyInt_AsLong(value);
	if (timestamp <= 0) {
		PyErr_SetString(PyExc_TypeError, "Timestamp must be a positive integer");
		return -1;
	}
	return pcm_ctl(self->pfp, PCMIOSETTIME, (int*)&timestamp);
}

static PyObject*
pcmfile_samplerate(PcmfileObject* self, void *closure)
{
	struct pcmstat s;
	pcm_stat(self->pfp, &s);
	return Py_BuildValue("i", s.samplerate);
}

static int
pcmfile_setsamplerate(PcmfileObject* self, PyObject *value, void *closure)
{
	int srate;
	if (value == NULL) {
		PyErr_SetString(PyExc_TypeError, "Cannot delete the samplerate attribute");
		return -1;
	}

	srate = (int)PyInt_AsLong(value);
	if (srate <= 0) {
		PyErr_SetString(PyExc_TypeError, "Sample rate must be a positive integer");
		return -1;
	}

	return pcm_ctl(self->pfp, PCMIOSETSR, (int*)&srate);
}

static PyObject*
pcmfile_nsamples(PcmfileObject* self, void *closure)
{
	struct pcmstat s;
	pcm_stat(self->pfp, &s);
	return Py_BuildValue("i", s.nsamples);
}

static PyObject*
pcmfile_entry(PcmfileObject* self, void *closure)
{
	return Py_BuildValue("i", self->pfp->entry);
}

static int
pcmfile_seek(PcmfileObject* self, PyObject* value, void *closure)
{
	int entry;
	if (value == NULL) {
	        PyErr_SetString(PyExc_TypeError, "Cannot delete the entry attribute");
		return -1;
	}

	entry = (int)PyInt_AsLong(value);
	if (pcm_seek(self->pfp, entry) != 0) {
		PyErr_SetString(PyExc_IOError, "Invalid entry");
		return -1;
	}

	return 0;
}

static PyObject*
pcmfile_read(PcmfileObject* self)
{
	/* allocate data */
 	int nsamples;
 	npy_intp shape[1];
	short *buf_p;
 	PyArrayObject *pcmdata;

	if (pcm_read(self->pfp, &buf_p, &nsamples) == -1) {
		PyErr_SetString(PyExc_IOError, "Unable to read from file.");
		return NULL;
	}
 	shape[0] = nsamples;

 	pcmdata  = (PyArrayObject*) PyArray_SimpleNew(1,shape,NPY_SHORT);
 	memcpy(PyArray_DATA(pcmdata), (void*)buf_p, nsamples * sizeof(short));

	return PyArray_Return(pcmdata);
}

static PyObject*
pcmfile_write(PcmfileObject* self, PyObject* args)
{
	PyObject* o;
	PyArrayObject* data;
	if (!PyArg_ParseTuple(args, "O", &o))
		return NULL;

	data = (PyArrayObject*) PyArray_FromAny(o, PyArray_DescrFromType(NPY_SHORT), 
						1, 1, NPY_CONTIGUOUS, NULL);
	if (data==NULL)
		return NULL;
	
	pcm_write(self->pfp, (short *)PyArray_DATA(data), PyArray_DIM(data, 0));
	Py_XDECREF(data);
	return Py_BuildValue("");
}
	
static PyGetSetDef pcmfile_getseters[]={
	{"nentries", (getter)pcmfile_nentries, 0, "The number of entries in the file", 0},
	{"framerate", (getter)pcmfile_samplerate, (setter)pcmfile_setsamplerate, 
	 "The sample rate of the current entry", 0},
	{"nframes", (getter)pcmfile_nsamples, 0, "The number of samples in the current entry",0},
	{"timestamp", (getter)pcmfile_timestamp, (setter)pcmfile_settimestamp, 
	 "The timestamp of the current entry",0},
	{"entry", (getter)pcmfile_entry, (setter)pcmfile_seek, "The current entry (set to seek to new entry)",0},
	{NULL}
};

static PyMethodDef pcmfile_methods[]= {
	{"read", (PyCFunction)pcmfile_read, METH_NOARGS,
	 "Read data from the current entry"},
	{"write", (PyCFunction)pcmfile_write, METH_VARARGS,
	 "Write data to the current entry"},
	{NULL}
};

static PyTypeObject PcmfileType = {
	PyObject_HEAD_INIT(NULL)
	0,                             /*ob_size*/
	"_pcmseqio.pcmfile",              /*tp_name*/
	sizeof(PcmfileObject), /*tp_basicsize*/
	0,                             /*tp_itemsize*/
	(destructor)pcmfile_dealloc,                         /*tp_dealloc*/
	0,                         /*tp_print*/
	0,                         /*tp_getattr*/
	0,                         /*tp_setattr*/
	0,                         /*tp_compare*/
	0,                         /*tp_repr*/
	0,                         /*tp_as_number*/
	0,                         /*tp_as_sequence*/
	0,                         /*tp_as_mapping*/
	0,                         /*tp_hash */
	0,                         /*tp_call*/
	0,                         /*tp_str*/
	0,                         /*tp_getattro*/
	0,                         /*tp_setattro*/
	0,                         /*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,        /*tp_flags*/
	"Wrapper class for pcm files",           /* tp_doc */
	0,		               /* tp_traverse */
	0,		               /* tp_clear */
	0,		               /* tp_richcompare */
	0,		               /* tp_weaklistoffset */
	0,		               /* tp_iter */
	0,		               /* tp_iternext */
	pcmfile_methods,             /* tp_methods */
	0,             /* tp_members */
	pcmfile_getseters,                         /* tp_getset */
	0,                         /* tp_base */
	0,                         /* tp_dict */
	0,                         /* tp_descr_get */
	0,                         /* tp_descr_set */
	0,                         /* tp_dictoffset */
	(initproc)pcmfile_init,      /* tp_init */
	0,                         /* tp_alloc */
	0,                 /* tp_new */
};

static PyMethodDef _pcmseqio_methods[] = {
	{NULL}  /* Sentinel */
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC
init_pcmseqio(void)
{
	import_array();
	PyObject* m;

	PcmfileType.tp_dict = Py_BuildValue("{s:O}", "_dtype", 
					    (PyObject *)PyArray_DescrFromType(NPY_SHORT));
	
	PcmfileType.tp_new = PyType_GenericNew;
	if (PyType_Ready(&PcmfileType) < 0)
		return;
	
	m = Py_InitModule3("_pcmseqio", _pcmseqio_methods,
                       "Handles pcmseq2 files");
	
	Py_INCREF(&PcmfileType);
	PyModule_AddObject(m, "pcmfile", (PyObject *)&PcmfileType);
}
